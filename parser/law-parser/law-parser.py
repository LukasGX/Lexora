import json
import re
from pathlib import Path
from lxml import etree


def normalize_text(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def local_name(element):
    return etree.QName(element).localname


def inline_text(element):
    """Extrahiert Text aus verschachtelten Formatierungselementen."""

    parts = []

    def walk(node):
        if node.text:
            parts.append(node.text)

        for child in node:
            if local_name(child) == "BR":
                parts.append("\n")
            else:
                walk(child)

            if child.tail:
                parts.append(child.tail)

    walk(element)
    return normalize_text("".join(parts))


def parse_blocks(element):
    """Verarbeitet Textblöcke, Listen und Abbildungen."""

    elements = []
    buffer = []

    def flush():
        content = normalize_text("".join(buffer))
        buffer.clear()

        if content:
            elements.append({
                "type": "text",
                "content": content
            })

    def walk(node):
        if node.text:
            buffer.append(node.text)

        for child in node:
            tag = local_name(child)

            if tag == "BR":
                buffer.append("\n")

            elif tag == "DL":
                flush()
                elements.append(parse_list(child))

            elif tag == "IMG":
                flush()

                elements.append({
                    "type": "image",
                    "src": child.get("SRC", ""),
                    "alt": child.get("alt", ""),
                    "width": child.get("Width"),
                    "height": child.get("Height"),
                    "align": child.get("Align", "center")
                })

            else:
                # Dazu gehören auch table, tbody, tr und entry.
                # Ihre Inhalte werden rekursiv verarbeitet.
                walk(child)

            if child.tail:
                buffer.append(child.tail)

    walk(element)
    flush()

    return elements


def parse_list(element):
    """Verarbeitet geordnete und ungeordnete Listen."""

    list_type = element.get("Type", "").lower()

    unordered_types = {
        "bullet",
        "dash",
        "unordered"
    }

    list_kind = (
        "unordered-list"
        if list_type in unordered_types
        else "ordered-list"
    )

    items = []
    marker = ""

    for child in element:
        tag = local_name(child)

        if tag == "DT":
            marker = inline_text(child)

        elif tag == "DD":
            items.append({
                "marker": marker,
                "elements": parse_blocks(child)
            })
            marker = ""

    return {
        "type": list_kind,
        "elements": items
    }


def parse_paragraph(element):
    """Verarbeitet einen einzelnen Gesetzesabsatz."""

    elements = parse_blocks(element)

    nr = None

    # Absatznummer am Anfang erkennen
    if elements and elements[0]["type"] == "text":
        match = re.match(
            r"^\s*\(([^)]+)\)\s*",
            elements[0]["content"]
        )

        if match:
            nr = match.group(1)

            elements[0]["content"] = (
                elements[0]["content"][match.end():]
            )

            if not elements[0]["content"]:
                elements.pop(0)

    if nr is not None:
        return {
            "type": "paragraph",
            "nr": nr,
            "elements": elements
        }

    # Einfache Textblöcke kompakt speichern
    if len(elements) == 1 and elements[0]["type"] == "text":
        return elements[0]

    return {
        "type": "text",
        "elements": elements
    }


def parse_law(xml_file, prefix="gg"):
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        recover=False
    )

    tree = etree.parse(str(xml_file), parser)
    root = tree.getroot()

    laws = []

    for norm in root.xpath(".//norm"):
        enbez = norm.findtext("metadaten/enbez") or ""
        title = norm.findtext("metadaten/titel") or ""

        # Inhalte aus den eigentlichen Gesetzestexten
        paragraphs = norm.xpath(
            "./textdaten/text//*[local-name()='P']"
        )

        contents = []

        for paragraph in paragraphs:
            result = parse_paragraph(paragraph)

            if result.get("content") or result.get("elements"):
                contents.append(result)

        # Normen ohne eigentlichen Gesetzestext ignorieren
        if not contents:
            continue

        # Artikel-/Paragraphennummer ermitteln
        match = re.search(
            r"(?:Artikel|Art\.?|§{1,2})\s*(\d+[a-zA-Z]?)",
            enbez,
            re.IGNORECASE
        )

        nr = match.group(1) if match else enbez

        # ID generieren
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", nr.lower()).strip("-")

        if slug.isdigit():
            slug = slug.zfill(5)

        law_id = f"{prefix}-{slug}"

        laws.append({
            "id": f"{prefix}-{slug}",
            "nr": nr,
            "name": title,
            "contents": contents
        })

    return laws


def main():
    input_file = Path("input.xml")
    output_file = Path("output.json")

    prefix = input("Enter prefix (book id): ")

    laws = parse_law(input_file, prefix=prefix)

    result = {
        "laws": laws
    }

    output_file.write_text(
        json.dumps(result, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"{len(laws)} Normen exportiert.")


if __name__ == "__main__":
    main()
