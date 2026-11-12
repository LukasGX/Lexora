import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("CLAUDE_MODEL")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"

MAX_TOKENS = 8192


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
    "id": "stgb-00123",
    "nr": "123",
    "name": "Hausfriedensbruch",
    "contents": [
        {
            "type": "paragraph",
            "nr": "1",
            "elements": [
                {
                    "type": "text",
                    "content": (
                        "Wer in die Wohnung, in die Geschäftsräume "
                        "oder in das befriedete Besitztum eines anderen "
                        "oder in abgeschlossene Räume, welche zum "
                        "öffentlichen Dienst oder Verkehr bestimmt sind, "
                        "widerrechtlich eindringt, oder wer, wenn er "
                        "ohne Befugnis darin verweilt, auf die Aufforderung "
                        "des Berechtigten sich nicht entfernt, wird mit "
                        "Freiheitsstrafe bis zu einem Jahr oder mit "
                        "Geldstrafe bestraft."
                    )
                }
            ]
        },
        {
            "type": "paragraph",
            "nr": "2",
            "elements": [
                {
                    "type": "text",
                    "content": "Die Tat wird nur auf Antrag verfolgt."
                }
            ]
        }
    ]
}


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
# Save output
# --------------------------------------------------

output_file = BASE_DIR / "test_result.json"

try:
    parsed_result = json.loads(result_text)

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(
            parsed_result,
            file,
            ensure_ascii=False,
            indent=4
        )

    print(f"\nResult saved to: {output_file}")

except json.JSONDecodeError:
    print("\nWARNING: Model did not return valid JSON.")
    print("Raw response was not saved as structured JSON.")
    (BASE_DIR / "test_result.txt").write_text(
        result_text,
        encoding="utf-8"
    )
