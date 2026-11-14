
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from jsonschema import Draft202012Validator


# ==================================================
# Configuration
# ==================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("ANTHROPIC_API_KEY")

HAIKU_MODEL = os.getenv(
    "CLAUDE_HAIKU_MODEL",
    os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
)

SONNET_MODEL = os.getenv(
    "CLAUDE_SONNET_MODEL",
    "claude-sonnet-5-5"
)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"

MAX_TOKENS = 16384
TIMEOUT = 180

# Unterhalb dieses Wertes wird eskaliert.
MIN_CONFIDENCE = 0.95

LAW_ID = "stgb-00263"

LAW_FILE = BASE_DIR / "laws" / "stgb.json"
SYSTEM_PROMPT_FILE = BASE_DIR / "summary_system_prompt.txt"
SCHEMA_FILE = BASE_DIR / "summary.schema.json"

OUTPUT_FILE = BASE_DIR / "test_result.json"
RAW_OUTPUT_FILE = BASE_DIR / "test_result.txt"
INVALID_OUTPUT_FILE = BASE_DIR / "test_result.invalid.json"

HUMAN_VERIFICATION_FILE = (
    BASE_DIR / "data" / "human_verification.json"
)


# ==================================================
# Configuration validation
# ==================================================

if not API_KEY:
    sys.exit("ANTHROPIC_API_KEY fehlt in .env")

for file in (
    LAW_FILE,
    SYSTEM_PROMPT_FILE,
    SCHEMA_FILE
):
    if not file.is_file():
        sys.exit(f"Datei nicht gefunden: {file}")

system_prompt = SYSTEM_PROMPT_FILE.read_text(
    encoding="utf-8"
)

schema = json.loads(
    SCHEMA_FILE.read_text(encoding="utf-8")
)


# ==================================================
# Load law
# ==================================================

lawbook = json.loads(
    LAW_FILE.read_text(encoding="utf-8")
)

laws = lawbook.get("laws", [])

law = next(
    (
        item for item in laws
        if item.get("id") == LAW_ID
    ),
    None
)

if law is None:
    sys.exit(f"Norm nicht gefunden: {LAW_ID}")


# ==================================================
# Validation
# ==================================================

def resolve_path(data, path):
    """Resolve a path relative to law['contents']."""

    current = data

    try:
        for key in path:
            current = current[key]

        return current

    except (KeyError, IndexError, TypeError):
        return None


def collect_statements(node):
    """Recursively collect all statements from a logic tree."""

    if not isinstance(node, dict):
        return []

    if "text" in node and "sources" in node:
        return [node]

    statements = []

    for item in node.get("items", []):
        statements.extend(collect_statements(item))

    return statements


def collect_all_statements(summary):
    statements = []

    for section in summary.get("sections", []):
        statements.extend(
            collect_statements(section.get("content", {}))
        )

    return statements


def validate_source(law, source):
    errors = []

    if not isinstance(source, dict):
        return ["Source is not an object"]

    path = source.get("element_path")
    quote = source.get("quote")
    paragraph_nr = source.get("paragraph")

    if not isinstance(path, list) or not path:
        return ["element_path is missing or invalid"]

    if not isinstance(path[0], int):
        return ["element_path must start with an integer"]

    element = resolve_path(law["contents"], path)

    if element is None:
        return [f"Invalid element_path: {path}"]

    if not isinstance(element, dict):
        return [f"Path does not resolve to an object: {path}"]

    if element.get("type") != "text":
        return [
            f"Path does not point to a text element: {path}"
        ]

    # Paragraph reference
    paragraph_index = path[0]

    try:
        actual_paragraph = law["contents"][paragraph_index]["nr"]

        if str(actual_paragraph) != str(paragraph_nr):
            errors.append(
                f"Paragraph mismatch: expected {paragraph_nr}, "
                f"actual {actual_paragraph}"
            )

    except (IndexError, KeyError, TypeError):
        errors.append(
            f"Could not verify paragraph number: {paragraph_nr}"
        )

    # Exact quote
    original_text = element.get("content", "")

    if not isinstance(quote, str) or not quote:
        errors.append("Quote is missing or empty")

    elif quote not in original_text:
        errors.append(
            f"Quote not found in referenced text: {quote!r}"
        )

    return errors


def validate_summary_schema(summary):
    validator = Draft202012Validator(schema)

    errors = sorted(
        validator.iter_errors(summary),
        key=lambda error: list(error.absolute_path)
    )

    return [
        f"{list(error.absolute_path)}: {error.message}"
        for error in errors
    ]


def validate_summary_sources(summary, law):
    errors = []

    statements = collect_all_statements(summary)

    if not statements:
        errors.append("No statements found in summary")

    source_count = 0

    for statement_index, statement in enumerate(
        statements, 1
    ):
        sources = statement.get("sources", [])

        if not isinstance(sources, list) or not sources:
            errors.append(
                f"Statement {statement_index} has no sources"
            )
            continue

        for source_index, source in enumerate(sources, 1):
            source_count += 1

            for error in validate_source(law, source):
                errors.append(
                    f"Statement {statement_index}, "
                    f"source {source_index}: {error}"
                )

    return errors, len(statements), source_count


def validate_quality(summary):
    """
    Deterministic quality checks.

    The model's own 'escalation' field is deliberately ignored.
    """

    errors = []

    quality = summary.get("quality")

    if not isinstance(quality, dict):
        return ["Missing or invalid quality object"]

    confidence = quality.get("confidence")

    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        errors.append(
            "Confidence must be a finite number between 0 and 1"
        )

    elif confidence < MIN_CONFIDENCE:
        errors.append(
            f"Confidence too low: {confidence} "
            f"(minimum: {MIN_CONFIDENCE})"
        )

    uncertainties = quality.get("uncertainties")

    if not isinstance(uncertainties, list):
        errors.append("Uncertainties must be an array")

    elif uncertainties:
        errors.append(
            f"Model reported {len(uncertainties)} uncertainty/ies"
        )

        for index, uncertainty in enumerate(uncertainties, 1):
            if not isinstance(uncertainty, str) or not uncertainty.strip():
                errors.append(
                    f"Uncertainty {index} is empty or invalid"
                )

    return errors


def validate_result(result, stop_reason):
    errors = []

    if stop_reason != "end_turn":
        errors.append(
            f"Incomplete model response: {stop_reason}"
        )

    if not isinstance(result, dict):
        errors.append("Result is not a JSON object")
        return errors

    # Schema
    errors.extend(
        f"Schema: {error}"
        for error in validate_summary_schema(result)
    )

    # Sources
    try:
        source_errors, _, _ = validate_summary_sources(
            result, law
        )
        errors.extend(source_errors)

    except (AttributeError, KeyError, TypeError) as error:
        errors.append(
            f"Source validation failed: {error}"
        )

    # Confidence and uncertainties
    errors.extend(validate_quality(result))

    return errors


# ==================================================
# API
# ==================================================

headers = {
    "x-api-key": API_KEY,
    "anthropic-version": API_VERSION,
    "content-type": "application/json"
}


def extract_json(text):
    """
    Extract JSON, including JSON surrounded by Markdown
    or additional explanatory text.
    """

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()

    for index, char in enumerate(text):
        if char != "{":
            continue

        try:
            result, _ = decoder.raw_decode(text[index:])
            return result

        except json.JSONDecodeError:
            continue

    raise ValueError("No valid JSON found in model response")


def call_model(model, tier):
    prompt = system_prompt.replace(
        "{{MODEL_TIER}}",
        tier
    )

    system = f"""
{prompt}

## JSON Schema

The following JSON Schema is mandatory.
Your output must conform to it.

{json.dumps(schema, ensure_ascii=False, indent=2)}
"""

    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Summarize the following legal provision "
                    "according to your system instructions.\n\n"
                    f"Current model tier: {tier}\n\n"
                    "Legal provision:\n"
                    + json.dumps(
                        law,
                        ensure_ascii=False,
                        indent=2
                    )
                )
            }
        ]
    }

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    text_blocks = [
        block["text"]
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]

    raw_text = "\n".join(text_blocks)

    return {
        "raw": raw_text,
        "data": data,
        "result": extract_json(raw_text),
        "stop_reason": data.get("stop_reason"),
        "usage": data.get("usage", {})
    }


# ==================================================
# Human verification
# ==================================================

def add_human_verification(
    law_id,
    sonnet_errors,
    haiku_errors,
    sonnet_result=None
):
    HUMAN_VERIFICATION_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if HUMAN_VERIFICATION_FILE.exists():
        entries = json.loads(
            HUMAN_VERIFICATION_FILE.read_text(
                encoding="utf-8"
            )
        )
    else:
        entries = []

    if not isinstance(entries, list):
        raise ValueError(
            "human_verification.json must contain a JSON array"
        )

    entry = {
        "law_id": law_id,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "model": SONNET_MODEL,
        "haiku_errors": haiku_errors,
        "sonnet_errors": sonnet_errors
    }

    entries.append(entry)

    temp_file = HUMAN_VERIFICATION_FILE.with_suffix(
        ".json.tmp"
    )

    temp_file.write_text(
        json.dumps(
            entries,
            ensure_ascii=False,
            indent=4
        ),
        encoding="utf-8"
    )

    temp_file.replace(HUMAN_VERIFICATION_FILE)

    if sonnet_result is not None:
        INVALID_OUTPUT_FILE.write_text(
            json.dumps(
                sonnet_result,
                ensure_ascii=False,
                indent=4
            ),
            encoding="utf-8"
        )


# ==================================================
# Pipeline
# ==================================================

def print_usage(label, usage):
    print(
        f"{label}: "
        f"{usage.get('input_tokens', 0)} input / "
        f"{usage.get('output_tokens', 0)} output tokens"
    )


def main():
    print(f"Law: {LAW_ID}")

    # ----------------------------------------------
    # First tier: Haiku
    # ----------------------------------------------

    try:
        haiku = call_model(
            HAIKU_MODEL,
            "haiku"
        )

        RAW_OUTPUT_FILE.write_text(
            haiku["raw"],
            encoding="utf-8"
        )

        haiku_errors = validate_result(
            haiku["result"],
            haiku["stop_reason"]
        )

    except Exception as error:
        haiku = None
        haiku_errors = [
            f"Haiku request or parsing failed: {error}"
        ]

    if not haiku_errors:
        OUTPUT_FILE.write_text(
            json.dumps(
                haiku["result"],
                ensure_ascii=False,
                indent=4
            ),
            encoding="utf-8"
        )

        print("Escalation: NO")
        print("Level: Haiku")
        print_usage("Haiku", haiku["usage"])
        return

    # ----------------------------------------------
    # Second tier: Sonnet
    # ----------------------------------------------

    try:
        sonnet = call_model(
            SONNET_MODEL,
            "sonnet"
        )

        sonnet_errors = validate_result(
            sonnet["result"],
            sonnet["stop_reason"]
        )

    except Exception as error:
        sonnet = None
        sonnet_errors = [
            f"Sonnet request or parsing failed: {error}"
        ]

    if not sonnet_errors:
        OUTPUT_FILE.write_text(
            json.dumps(
                sonnet["result"],
                ensure_ascii=False,
                indent=4
            ),
            encoding="utf-8"
        )

        print("Escalation: YES")
        print("Level: Sonnet")
        print_usage("Haiku", haiku["usage"] if haiku else {})
        print_usage("Sonnet", sonnet["usage"])
        return

    # ----------------------------------------------
    # Human verification
    # ----------------------------------------------

    add_human_verification(
        law_id=LAW_ID,
        sonnet_errors=sonnet_errors,
        haiku_errors=haiku_errors,
        sonnet_result=(
            sonnet["result"] if sonnet else None
        )
    )

    print("Escalation: YES")
    print("Level: Human verification")

    print(
        f"Human verification entry: "
        f"{HUMAN_VERIFICATION_FILE}"
    )

    if sonnet:
        print_usage("Haiku", haiku["usage"] if haiku else {})
        print_usage("Sonnet", sonnet["usage"])


if __name__ == "__main__":
    main()
