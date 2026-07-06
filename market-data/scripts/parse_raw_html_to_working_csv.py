#!/usr/bin/env python3
"""Convert locally saved Shimamura/Ishibashi purchase-price HTML into a working CSV.

This script intentionally does not access the network. Put saved HTML files under:
  market-data/raw-html/shimamura/
  market-data/raw-html/ishibashi/

The parser is heuristic because public pages can differ by category. It extracts HTML
text/table rows and looks for brand, model, condition rank, and yen prices.
Rows that cannot be parsed are written to an error report.
"""
from __future__ import annotations

import argparse
import csv
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

WORK_COLUMNS = [
    "source_name",
    "source_url",
    "instrument_category",
    "brand_name",
    "model_name",
    "condition_label",
    "source_price",
    "checked_date",
    "memo",
]

CATEGORY_KEYWORDS = {
    "エレキギター": ["エレキ", "electric", "eguitar", "e-guitar"],
    "アコースティックギター": ["アコースティック", "アコギ", "acoustic", "aguitar", "a-guitar"],
    "ベース": ["ベース", "bass"],
    "サックス": ["サックス", "sax"],
    "電子ピアノ": ["電子ピアノ", "digital-piano", "epiano", "piano"],
    "フルート": ["フルート", "flute"],
    "クラリネット": ["クラリネット", "clarinet"],
}
CONDITION_PATTERNS = ["Aランク", "Bランク", "Cランク", "美品", "良品", "並品"]
PRICE_RE = re.compile(r"(?:買取価格|上限|税込)?\s*[¥￥]?\s*([0-9０-９][0-9０-９,，]{2,})\s*円?")
SOURCE_MAP_COLUMNS = ["file_path", "source_name", "source_url", "instrument_category"]


def normalize_digits(value: str) -> str:
    return value.translate(str.maketrans("０１２３４５６７８９，", "0123456789,"))


class TextTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.rows: list[list[str]] = []
        self._in_cell = False
        self._cell: list[str] = []
        self._row: list[str] | None = None

    def handle_starttag(self, tag: str, attrs):
        if tag == "tr":
            self._row = []
        if tag in {"td", "th"}:
            self._in_cell = True
            self._cell = []
        for name, value in attrs:
            if name in {"href", "data-url"} and value:
                self.text_parts.append(value)

    def handle_endtag(self, tag: str):
        if tag in {"td", "th"} and self._in_cell:
            cell = " ".join("".join(self._cell).split())
            if self._row is not None:
                self._row.append(cell)
            self._in_cell = False
        if tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
        if tag in {"p", "li", "div", "br", "tr"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str):
        self.text_parts.append(data)
        if self._in_cell:
            self._cell.append(data)


def guess_category(path: Path, text: str) -> str:
    haystack = f"{path.name} {text[:2000]}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    return ""


def split_item_name(name: str) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", name).strip(" -:：｜|")
    if not cleaned:
        return "", ""
    parts = cleaned.split(" ", 1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


def parse_candidate(text: str) -> tuple[str, str, str, int] | None:
    condition = next((c for c in CONDITION_PATTERNS if c in text), "")
    price_match = PRICE_RE.search(normalize_digits(text))
    if not price_match:
        return None
    price = int(price_match.group(1).replace(",", ""))
    name = text
    for token in CONDITION_PATTERNS:
        name = name.replace(token, " ")
    name = PRICE_RE.sub(" ", normalize_digits(name))
    name = re.sub(r"(買取価格|上限|税込|円|ランク|査定)", " ", name)
    brand, model = split_item_name(name)
    return brand, model, condition, price


def row_texts(parser: TextTableParser, full_text: str) -> Iterable[str]:
    for row in parser.rows:
        joined = " ".join(cell for cell in row if cell)
        if joined:
            yield joined
    for line in full_text.splitlines():
        line = " ".join(line.split())
        if line:
            yield line


def parse_file(
    path: Path,
    source_name: str,
    checked_date: str,
    source_url: str = "",
    instrument_category: str = "",
) -> tuple[list[dict], list[dict]]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    parser = TextTableParser()
    parser.feed(html)
    text = "".join(parser.text_parts)
    category = instrument_category or guess_category(path, text)
    parsed: list[dict] = []
    errors: list[dict] = []
    seen: set[tuple] = set()

    for candidate in row_texts(parser, text):
        if not any(cond in candidate for cond in CONDITION_PATTERNS) or not PRICE_RE.search(normalize_digits(candidate)):
            continue
        result = parse_candidate(candidate)
        if not result:
            errors.append({"file": str(path), "reason": "price_or_item_not_parsed", "raw_text": candidate})
            continue
        brand, model, condition, price = result
        if not (brand and model and condition and price):
            errors.append({"file": str(path), "reason": "missing_required_field", "raw_text": candidate})
            continue
        key = (brand, model, condition, price)
        if key in seen:
            continue
        seen.add(key)
        parsed.append({
            "source_name": source_name,
            "source_url": source_url,
            "instrument_category": category,
            "brand_name": brand,
            "model_name": model,
            "condition_label": condition,
            "source_price": price,
            "checked_date": checked_date,
            "memo": f"parsed_from={path.name}",
        })
    if not parsed:
        errors.append({"file": str(path), "reason": "no_rows_parsed", "raw_text": text[:500].replace("\n", " ")})
    return parsed, errors


def normalize_map_path(value: str) -> str:
    return str(Path(value.strip()).as_posix()).lstrip("./")


def load_source_map(raw_dir: Path, map_path: Path) -> tuple[dict[str, dict[str, str]], list[dict]]:
    mapping: dict[str, dict[str, str]] = {}
    errors: list[dict] = []
    if not map_path.exists():
        return mapping, errors
    with open(map_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [col for col in SOURCE_MAP_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            errors.append({"file": str(map_path), "reason": "source_map_missing_columns", "raw_text": ",".join(missing)})
            return mapping, errors
        for line_no, row in enumerate(reader, start=2):
            file_path = normalize_map_path(row.get("file_path", ""))
            if not file_path:
                errors.append({"file": str(map_path), "reason": "source_map_blank_file_path", "raw_text": f"line={line_no}"})
                continue
            mapping[file_path] = {
                "source_name": row.get("source_name", "").strip(),
                "source_url": row.get("source_url", "").strip(),
                "instrument_category": row.get("instrument_category", "").strip(),
            }
            filename_key = Path(file_path).name
            mapping.setdefault(filename_key, mapping[file_path])
    return mapping, errors


def source_from_path(path: Path, raw_dir: Path) -> str:
    try:
        return path.relative_to(raw_dir).parts[0]
    except (ValueError, IndexError):
        return path.parent.name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="market-data/raw-html")
    parser.add_argument("--output", default="market-data/working/working_prices.csv")
    parser.add_argument("--errors", default="market-data/working/parse_errors.csv")
    parser.add_argument("--checked-date", default=date.today().isoformat())
    parser.add_argument("--source-map", default="", help="CSV mapping file_path,source_name,source_url,instrument_category. Defaults to <raw-dir>/source_map.csv when present.")
    parser.add_argument("--source-url", default="", help="Fallback source_url used only when source_map.csv has no entry for a file.")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    source_map_path = Path(args.source_map) if args.source_map else raw_dir / "source_map.csv"
    source_map, source_map_errors = load_source_map(raw_dir, source_map_path)

    rows: list[dict] = []
    errors: list[dict] = source_map_errors
    html_paths = sorted(path for path in raw_dir.glob("**/*") if path.suffix.lower() in {".html", ".htm"})
    for path in html_paths:
        rel_path = normalize_map_path(str(path.relative_to(raw_dir)))
        map_row = source_map.get(rel_path) or source_map.get(path.name) or {}
        source_name = map_row.get("source_name") or source_from_path(path, raw_dir)
        source_url = map_row.get("source_url") or args.source_url
        instrument_category = map_row.get("instrument_category", "")
        parsed, parse_errors = parse_file(
            path,
            source_name,
            args.checked_date,
            source_url=source_url,
            instrument_category=instrument_category,
        )
        rows.extend(parsed)
        errors.extend(parse_errors)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=WORK_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    Path(args.errors).parent.mkdir(parents=True, exist_ok=True)
    with open(args.errors, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "reason", "raw_text"])
        writer.writeheader()
        writer.writerows(errors)

    print(f"wrote {len(rows)} rows to {args.output}; {len(errors)} errors to {args.errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
