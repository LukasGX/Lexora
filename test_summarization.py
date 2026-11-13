import json
import os
import sys
from pathlib import Path
from jsonschema import Draft202012Validator

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"

MAX_TOKENS = 16384


# --------------------------------------------------
# Input
# --------------------------------------------------

SYSTEM_PROMPT_FILE = BASE_DIR / "summary_system_prompt.txt"
SCHEMA_FILE = BASE_DIR / "summary.schema.json"

if not API_KEY:
    sys.exit("ERROR: ANTHROPIC_API_KEY fehlt in .env")

if not SYSTEM_PROMPT_FILE.is_file():
    sys.exit("ERROR: summary_system_prompt.txt nicht gefunden")

if not SCHEMA_FILE.is_file():
    sys.exit("ERROR: summary.schema.json nicht gefunden")


system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


law = {
    "id": "stgb-00263",
    "nr": "263",
    "name": "Betrug",
    "contents": [
        {
            "type": "paragraph",
            "nr": "1",
            "elements": [
                {
                    "type": "text",
                    "content": "Wer in der Absicht, sich oder einem Dritten einen rechtswidrigen Vermögensvorteil zu verschaffen, das Vermögen eines anderen dadurch beschädigt, daß er durch Vorspiegelung falscher oder durch Entstellung oder Unterdrückung wahrer Tatsachen einen Irrtum erregt oder unterhält, wird mit Freiheitsstrafe bis zu fünf Jahren oder mit Geldstrafe bestraft."
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "2",
            "elements": [
                {
                    "type": "text",
                    "content": "Der Versuch ist strafbar."
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "3",
            "elements": [
                {
                    "type": "text",
                    "content": "In besonders schweren Fällen ist die Strafe Freiheitsstrafe von sechs Monaten bis zu zehn Jahren. Ein besonders schwerer Fall liegt in der Regel vor, wenn der Täter"
                },
                {
                    "type": "ordered-list",
                    "elements": [
                        {
                            "marker": "1.",
                            "elements": [
                                {
                                    "type": "text",
                                    "content": "gewerbsmäßig oder als Mitglied einer Bande handelt, die sich zur fortgesetzten Begehung von Urkundenfälschung oder Betrug verbunden hat,"
                                }
                            ]
                        },
                        {
                            "marker": "2.",
                            "elements": [
                                {
                                    "type": "text",
                                    "content": "einen Vermögensverlust großen Ausmaßes herbeiführt oder in der Absicht handelt, durch die fortgesetzte Begehung von Betrug eine große Zahl von Menschen in die Gefahr des Verlustes von Vermögenswerten zu bringen,"
                                }
                            ]
                        },
                        {
                            "marker": "3.",
                            "elements": [
                                {
                                    "type": "text",
                                    "content": "eine andere Person in wirtschaftliche Not bringt,"
                                }
                            ]
                        },
                        {
                            "marker": "4.",
                            "elements": [
                                {
                                    "type": "text",
                                    "content": "seine Befugnisse oder seine Stellung als Amtsträger oder Europäischer Amtsträger mißbraucht oder"
                                }
                            ]
                        },
                        {
                            "marker": "5.",
                            "elements": [
                                {
                                    "type": "text",
                                    "content": "einen Versicherungsfall vortäuscht, nachdem er oder ein anderer zu diesem Zweck eine Sache von bedeutendem Wert in Brand gesetzt oder durch eine Brandlegung ganz oder teilweise zerstört oder ein Schiff zum Sinken oder Stranden gebracht hat."
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "4",
            "elements": [
                {
                    "type": "text",
                    "content": "§ 243 Abs. 2 sowie die §§ 247 und 248a gelten entsprechend."
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "5",
            "elements": [
                {
                    "type": "text",
                    "content": "Mit Freiheitsstrafe von einem Jahr bis zu zehn Jahren, in minder schweren Fällen mit Freiheitsstrafe von sechs Monaten bis zu fünf Jahren wird bestraft, wer den Betrug als Mitglied einer Bande, die sich zur fortgesetzten Begehung von Straftaten nach den §§ 263 bis 264 oder 267 bis 269 verbunden hat, gewerbsmäßig begeht."
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "6",
            "elements": [
                {
                    "type": "text",
                    "content": "Das Gericht kann Führungsaufsicht anordnen (§ 68 Abs. 1)."
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "7",
            "elements": [
                {
                    "type": "text",
                    "content": "(weggefallen)"
                }
            ]
        }
    ]
}

# --------------------------------------------------
# Validation
# --------------------------------------------------

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
    """Collect statements from all summary sections."""

    statements = []

    for section in summary.get("sections", []):
        statements.extend(
            collect_statements(section.get("content", {}))
        )

    return statements


def validate_source(law, source):
    """Validate one source reference."""

    errors = []

    path = source.get("element_path")
    quote = source.get("quote")
    paragraph_nr = source.get("paragraph")

    if not isinstance(path, list) or not path:
        return ["element_path is missing or invalid"]

    # Paths must be relative to law['contents'].
    element = resolve_path(law["contents"], path)

    if element is None:
        return [f"Invalid element_path: {path}"]

    if not isinstance(element, dict):
        return [f"Path does not resolve to an object: {path}"]

    if element.get("type") != "text":
        errors.append(
            f"Path does not point to a text element: {path}"
        )
        return errors

    # Verify paragraph number.
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

    # Verify exact quote.
    original_text = element.get("content", "")

    if not isinstance(quote, str) or not quote:
        errors.append("Quote is missing or empty")

    elif quote not in original_text:
        errors.append(
            f"Quote not found in referenced text: {quote!r}"
        )

    return errors


def validate_summary_schema(summary, schema):
    """Validate summary against JSON Schema."""

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
    """Validate every source in every statement."""

    errors = []
    statements = collect_all_statements(summary)

    if not statements:
        errors.append("No statements found in summary")

    source_count = 0

    for statement_index, statement in enumerate(statements, 1):
        sources = statement.get("sources", [])

        if not sources:
            errors.append(
                f"Statement {statement_index} has no sources"
            )
            continue

        for source_index, source in enumerate(sources, 1):
            source_count += 1

            source_errors = validate_source(law, source)

            for error in source_errors:
                errors.append(
                    f"Statement {statement_index}, "
                    f"source {source_index}: {error}"
                )

    return errors, len(statements), source_count

# --------------------------------------------------
# API Request
# --------------------------------------------------

system = f"""
{system_prompt}

## JSON Schema

The following JSON Schema is mandatory.
Your output must conform to it.

{json.dumps(schema, ensure_ascii=False, indent=2)}
"""

payload = {
    "model": MODEL,
    "max_tokens": MAX_TOKENS,
    "system": system,
    "messages": [
        {
            "role": "user",
            "content": (
                "Summarize the following legal provision according "
                "to your system instructions.\n\n"
                "Current model tier: haiku\n\n"
                "Legal provision:\n"
                + json.dumps(law, ensure_ascii=False, indent=2)
            )
        }
    ]
}

headers = {
    "x-api-key": API_KEY,
    "anthropic-version": API_VERSION,
    "content-type": "application/json"
}


print(f"Model: {MODEL}")
print(f"Law: {law['id']}")
print("Sending request...\n")

try:
    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=180
    )

    response.raise_for_status()

except requests.exceptions.HTTPError:
    print("API Error:")
    print(response.status_code)
    print(response.text)
    sys.exit(1)

except requests.exceptions.RequestException as error:
    sys.exit(f"Request failed: {error}")

# --------------------------------------------------
# Response
# --------------------------------------------------

data = response.json()

content = data.get("content", [])

text_blocks = [
    block["text"]
    for block in content
    if block.get("type") == "text"
]

result_text = "\n".join(text_blocks)

print("=" * 60)
print("MODEL OUTPUT")
print("=" * 60)
print(result_text)


# --------------------------------------------------
# Usage
# --------------------------------------------------

usage = data.get("usage", {})

print("\n" + "=" * 60)
print("TOKEN USAGE")
print("=" * 60)

print(f"Input tokens:       {usage.get('input_tokens', 0)}")
print(f"Output tokens:      {usage.get('output_tokens', 0)}")
print(f"Cache creation:     {usage.get('cache_creation_input_tokens', 0)}")
print(f"Cache read:         {usage.get('cache_read_input_tokens', 0)}")

print(f"\nStop reason: {data.get('stop_reason')}")


# --------------------------------------------------
# Validation and Save
# --------------------------------------------------

output_file = BASE_DIR / "test_result.json"
raw_output_file = BASE_DIR / "test_result.txt"
invalid_output_file = BASE_DIR / "test_result.invalid.json"

checks = {
    "JSON parsing": False,
    "JSON Schema": False,
    "Element paths": False,
    "Text elements": False,
    "Exact quotes": False,
    "Paragraph references": False,
}

validation_errors = []

# Always preserve the original model output.
raw_output_file.write_text(
    result_text,
    encoding="utf-8"
)

# Check whether the model completed its response.
stop_reason = data.get("stop_reason")

if stop_reason != "end_turn":
    validation_errors.append(
        f"Incomplete model response: stop_reason={stop_reason}"
    )

# 1. JSON parsing
try:
    parsed_result = json.loads(result_text)
    checks["JSON parsing"] = True

except json.JSONDecodeError as error:
    parsed_result = None

    validation_errors.append(
        f"JSON parsing failed: {error}"
    )


if parsed_result is not None:

    # 2. JSON Schema
    schema_errors = validate_summary_schema(
        parsed_result,
        schema
    )

    checks["JSON Schema"] = not schema_errors
    validation_errors.extend(
        f"Schema: {error}"
        for error in schema_errors
    )

    # 3–6. Source validation
    source_errors, statement_count, source_count = (
        validate_summary_sources(parsed_result, law)
    )

    path_errors = [
        error for error in source_errors
        if "Invalid element_path" in error
        or "Path does not resolve" in error
    ]

    text_errors = [
        error for error in source_errors
        if "does not point to a text element" in error
    ]

    quote_errors = [
        error for error in source_errors
        if "Quote is missing" in error
        or "Quote not found" in error
    ]

    paragraph_errors = [
        error for error in source_errors
        if "Paragraph mismatch" in error
        or "Could not verify paragraph" in error
    ]

    checks["Element paths"] = not path_errors
    checks["Text elements"] = not text_errors
    checks["Exact quotes"] = not quote_errors
    checks["Paragraph references"] = not paragraph_errors

    validation_errors.extend(source_errors)

    print("\nStatements:", statement_count)
    print("Sources:", source_count)


# --------------------------------------------------
# Validation Report
# --------------------------------------------------

print("\n" + "=" * 60)
print("VALIDATION REPORT")
print("=" * 60)

for name, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")

print("\n" + "=" * 60)

if validation_errors:
    print(f"VALIDATION FAILED ({len(validation_errors)} errors)")

    for error in validation_errors:
        print(f"- {error}")

    if parsed_result is not None:
        invalid_output_file.write_text(
            json.dumps(
                parsed_result,
                ensure_ascii=False,
                indent=4
            ),
            encoding="utf-8"
        )

        print(
            f"\nInvalid result saved to: {invalid_output_file}"
        )

    print(f"Raw output saved to: {raw_output_file}")

else:
    with output_file.open("w", encoding="utf-8") as file:
        json.dump(
            parsed_result,
            file,
            ensure_ascii=False,
            indent=4
        )

    print("ALL CHECKS PASSED")
    print(f"Result saved to: {output_file}")