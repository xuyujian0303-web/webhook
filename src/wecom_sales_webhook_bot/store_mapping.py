from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree


def load_store_name_mapping(path: str | Path | None) -> dict[str, str]:
    """Read column 1 -> column 3 from the supplied XLSX without extra deps."""
    if not path:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with ZipFile(path) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall("m:si", ns):
                    shared.append("".join(x.text or "" for x in item.iter() if x.tag.endswith("}t")))
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            sheet_name = workbook.find("m:sheets/m:sheet", ns)
            rel_id = sheet_name.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            target = next(x.attrib["Target"] for x in rels if x.attrib.get("Id") == rel_id)
            sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            root = ElementTree.fromstring(archive.read(sheet_path))
            rows: list[list[str]] = []
            for row in root.findall("m:sheetData/m:row", ns):
                values: dict[int, str] = {}
                for cell in row.findall("m:c", ns):
                    ref = cell.attrib.get("r", "A1")
                    col = 0
                    for char in ref:
                        if char.isalpha(): col = col * 26 + ord(char.upper()) - 64
                        else: break
                    col -= 1
                    value = cell.find("m:v", ns)
                    text = value.text if value is not None and value.text else ""
                    if cell.attrib.get("t") == "s" and text.isdigit() and int(text) < len(shared):
                        text = shared[int(text)]
                    values[col] = text.strip()
                rows.append([values.get(i, "") for i in range(3)])
            return {row[0]: row[2] for row in rows[1:] if row[0] and row[2]}
    except (OSError, KeyError, ElementTree.ParseError, StopIteration):
        return {}
