import json
import re

from pathlib import Path
from collections import defaultdict
from itertools import product


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
LAWS_DIR = BASE_DIR / "laws"

# --------------------------------------------------
# Regular expressions
# --------------------------------------------------

REFERENCE_FRAGMENT = re.compile(
    r"(?P<kind>Absatz|Abs\.|Satz|S\.|Nummer|Nr\.)\s*"
    r"(?P<values>\d+[a-z]?(?:\s*(?:,|und|oder|bis)\s*\d+[a-z]?)*)",
    re.IGNORECASE
)


def normalize_number(value: str) -> str:
    return value.strip().lower()


def get_law_kind(book: dict) -> str:
    prefix = str(book.get("prefix", "§")).strip().lower()

    if prefix.startswith("art"):
        return "article"

    return "paragraph"


# --------------------------------------------------
# Loading
# --------------------------------------------------

def load_lawbooks() -> dict:
    books = {}

    for file in LAWS_DIR.glob("*.json"):
        if file.name.endswith(".link.json"):
            continue

        with file.open("r", encoding="utf-8") as f:
            book = json.load(f)

        book_id = book.get("id")

        if not book_id:
            print(f"[WARN] No book id in {file.name}")
            continue

        books[book_id] = book

    return books


# --------------------------------------------------
# Index
# --------------------------------------------------

def build_law_index(books: dict):
    index = {}
    abbreviations = {}

    for book_id, book in books.items():
        abbreviation = str(book.get("abbr", "")).strip()

        if abbreviation:
            abbreviations[abbreviation.lower()] = book_id

        kind = get_law_kind(book)

        for law in book.get("laws", []):
            number = normalize_number(str(law.get("nr", "")))

            if not number:
                continue

            key = (book_id, kind, number)

            # Doppelte Normnummern nicht stillschweigend überschreiben
            if key in index:
                print(f"[WARN] Double norm number: {book_id} {number}")
                continue

            index[key] = law

    return index, abbreviations

def normalize_name(value: str) -> str:
    return (
        value.lower()
        .replace("ß", "ss")
        .strip()
    )


def token_variants(token: str, is_last: bool) -> set[str]:
    token = normalize_name(token)
    variants = {token}

    # Adjektivische Endungen:
    # Bürgerliches -> Bürgerlichen, Bürgerlichem usw.
    if not is_last:
        if token.endswith("es"):
            stem = token[:-2]
            variants.update(
                stem + ending
                for ending in ("e", "en", "em", "er", "es")
            )
        elif token.endswith("e"):
            stem = token[:-1]
            variants.update(
                stem + ending
                for ending in ("e", "en", "em", "er", "es")
            )

    # Genitivformen des letzten Wortes:
    # Gesetzbuch -> Gesetzbuches / Gesetzbuchs
    else:
        variants.add(token + "s")
        variants.add(token + "es")

    return variants


def token_regex(token: str) -> str:
    """
    Allows ss and ß to match each other.
    """
    token = normalize_name(token)
    result = []
    i = 0

    while i < len(token):
        if token[i:i + 2] == "ss":
            result.append("(?:ss|ß)")
            i += 2
        else:
            result.append(re.escape(token[i]))
            i += 1

    return "".join(result)


def build_name_aliases(books: dict) -> list:
    aliases = []

    connectors = (
        "des", "der", "dem", "den",
        "die", "das", "im", "ins",
        "in dem", "in der", "in den",
        "vom", "von", "zum", "zur",
        "nach dem", "nach der",
        "gemäß dem", "gemäß der",
        "gemaess dem", "gemaess der"
    )

    connector_pattern = "|".join(
        re.escape(value)
        for value in sorted(connectors, key=len, reverse=True)
    )

    for book_id, book in books.items():
        names = {
            str(book.get("name", "")).strip(),
            str(book.get("abbr", "")).strip()
        }

        for name in names:
            if not name:
                continue

            # Leading articles in metadata are not needed.
            name = re.sub(
                r"^(der|die|das)\s+",
                "",
                name,
                flags=re.IGNORECASE
            )

            tokens = normalize_name(name).split()

            if not tokens:
                continue

            variants = [
                sorted(token_variants(token, i == len(tokens) - 1))
                for i, token in enumerate(tokens)
            ]

            # Generate combinations of grammatical variants.
            for combination in product(*variants):
                name_pattern = r"\s+".join(
                    token_regex(token)
                    for token in combination
                )

                pattern = re.compile(
                    rf"""
                    \s*
                    (?:(?:{connector_pattern})\s+)?
                    (?P<name>{name_pattern})
                    (?!\w)
                    """,
                    re.IGNORECASE | re.VERBOSE
                )

                aliases.append({
                    "book": book_id,
                    "pattern": pattern,
                    "length": len(name)
                })

    # Prefer longer, more specific names.
    aliases.sort(
        key=lambda item: item["length"],
        reverse=True
    )

    return aliases


# --------------------------------------------------
# Reference matching
# --------------------------------------------------

def build_reference_pattern() -> re.Pattern:
    return re.compile(
        r"""
        (?<![\w§])
        (?P<kind>§(?!§)|Art(?:ikel)?\.?)
        \s*
        (?P<number>\d+[a-z]?)

        (?P<fragment>
            (?:
                \s+
                (?:Absatz|Abs\.|Satz|S\.|Nummer|Nr\.)
                \s*
                \d+[a-z]?
                (?:
                    \s*(?:,|und|oder|bis)\s*\d+[a-z]?
                )*
            )*
        )
        """,
        re.IGNORECASE | re.VERBOSE
    )

def parse_fragment(fragment: str) -> dict:
    result = {}

    for match in REFERENCE_FRAGMENT.finditer(fragment):
        kind = match.group("kind").lower()
        values = re.findall(
            r"\d+[a-z]?",
            match.group("values"),
            re.IGNORECASE
        )

        if kind in ("absatz", "abs."):
            key = "paragraph"
        elif kind in ("satz", "s."):
            key = "sentences"
        else:
            key = "numbers"

        if key == "paragraph":
            result[key] = values[0] if values else None
        else:
            result[key] = values

    return result

def resolve_book_name(text: str, position: int, aliases: list):
    for alias in aliases:
        match = alias["pattern"].match(text, position)

        if match:
            return alias["book"], match.end()

    return None, position

def resolve_reference(
    match: re.Match,
    text: str,
    current_book_id: str,
    index: dict,
    aliases: list
):
    kind_text = match.group("kind").lower()
    number = normalize_number(match.group("number"))

    kind = (
        "article"
        if kind_text.startswith("art")
        else "paragraph"
    )

    # Explicit law name takes precedence over current book.
    target_book_id, reference_end = resolve_book_name(
        text,
        match.end(),
        aliases
    )

    if target_book_id is None:
        target_book_id = current_book_id

    target = index.get(
        (target_book_id, kind, number)
    )

    if target is None:
        return None

    return {
        "target": {
            "book": target_book_id,
            "law": target["id"]
        },
        "end": reference_end
    }


# --------------------------------------------------
# Recursive element traversal
# --------------------------------------------------

def walk_elements(node, path=()):
    """
    Finds every text element recursively.

    The path identifies the exact element in the
    original JSON structure.
    """

    if isinstance(node, list):
        for i, item in enumerate(node):
            yield from walk_elements(item, path + (i,))

    elif isinstance(node, dict):
        if (
            node.get("type") == "text"
            and isinstance(node.get("content"), str)
        ):
            yield path, node["content"]

        for key, value in node.items():
            if key == "content":
                continue

            yield from walk_elements(
                value,
                path + (key,)
            )


# --------------------------------------------------
# Parsing
# --------------------------------------------------

def parse_text(
    text: str,
    element_path: tuple,
    source_id: str,
    current_book_id: str,
    index: dict,
    aliases: list,
    reference_pattern: re.Pattern
):
    references = []

    for match in reference_pattern.finditer(text):
        resolved = resolve_reference(
            match=match,
            text=text,
            current_book_id=current_book_id,
            index=index,
            aliases=aliases
        )

        if resolved is None:
            continue

        fragment = parse_fragment(
            match.group("fragment")
        )

        references.append({
            "text": text[match.start():resolved["end"]],
            "start": match.start(),
            "end": resolved["end"],
            "target": resolved["target"],
            "fragment": fragment or None
        })

    if not references:
        return None

    return {
        "source": source_id,
        "element_path": list(element_path),
        "references": references
    }


def parse_lawbook(
    book_id: str,
    book: dict,
    index: dict,
    aliases: list,
    reference_pattern: re.Pattern
):
    links = []

    for law in book.get("laws", []):
        source_id = law.get("id")

        if not source_id:
            continue

        for path, text in walk_elements(law.get("contents", [])):
            result = parse_text(
                text=text,
                element_path=path,
                source_id=source_id,
                current_book_id=book_id,
                index=index,
                aliases=aliases,
                reference_pattern=reference_pattern
            )

            if result:
                links.append(result)

    return {
        "version": 1,
        "book": book_id,
        "links": links
    }


# --------------------------------------------------
# Saving
# --------------------------------------------------

def save_links(book_id: str, data: dict):
    output_file = LAWS_DIR / f"{book_id}.link.json"

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )

    print(
        f"[OK] {output_file.name}: "
        f"{len(data['links'])} elements with links"
    )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("Loading lawbooks ...")

    books = load_lawbooks()

    print(f"Loaded {len(books)} lawbooks.")

    index, abbreviations = build_law_index(books)
    aliases = build_name_aliases(books)
    reference_pattern = build_reference_pattern()

    print(f"Indexed {len(index)} norms.")

    for book_id, book in books.items():
        print(f"\nParsing {book_id} ...")

        data = parse_lawbook(
            book_id=book_id,
            book=book,
            index=index,
            aliases=aliases,
            reference_pattern=reference_pattern
        )

        save_links(book_id, data)

    print("\nFinished.")


if __name__ == "__main__":
    main()