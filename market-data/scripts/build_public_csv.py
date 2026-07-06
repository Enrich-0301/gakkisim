#!/usr/bin/env python3
"""Build simulator-ready public CSV from the working purchase-price CSV."""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

WORK_COLUMNS = ["source_name","source_url","instrument_category","brand_name","model_name","condition_label","source_price","checked_date","memo"]
PUBLIC_COLUMNS = ["instrument_category","brand_name","model_name","display_name","price_good","price_normal","price_used","price_min","price_max","data_type","updated_month","is_active","brand_aliases","model_aliases","search_keywords"]
CONDITION_TO_PRICE = {
    "shimamura": {"Aランク": "price_good", "Bランク": "price_normal", "Cランク": "price_used"},
    "ishibashi": {"美品": "price_good", "良品": "price_normal", "並品": "price_used"},
}
OFFICIAL_BOTH_AVG = "official_both_avg"
OFFICIAL_SINGLE_ADJUSTED = "official_single_adjusted"
MANUAL_ADJUSTED = "manual_adjusted"
ALLOWED_DATA_TYPES = {
    OFFICIAL_BOTH_AVG,
    OFFICIAL_SINGLE_ADJUSTED,
    MANUAL_ADJUSTED,
    "similar_model_reference",
    "brand_category_estimate",
}
PRICE_COLUMNS = ["price_good", "price_normal", "price_used"]


def round_1000(value: float) -> int:
    return int(math.floor((value + 500) / 1000) * 1000)


def normalized_price(prices_by_source: dict[str, list[int]]) -> tuple[int | None, str | None]:
    """Return a rounded public price and the official-data derivation type."""
    source_avgs = {source: sum(values) / len(values) for source, values in prices_by_source.items() if values}
    if not source_avgs:
        return None, None
    if len(source_avgs) >= 2:
        return round_1000(sum(source_avgs.values()) / len(source_avgs)), OFFICIAL_BOTH_AVG
    return round_1000(next(iter(source_avgs.values())) * 0.95), OFFICIAL_SINGLE_ADJUSTED


def row_data_type(price_data_types: dict[str, str | None]) -> str:
    """Collapse per-condition derivation types into a single public row data_type."""
    values = set(price_data_types.values())
    if values == {OFFICIAL_BOTH_AVG}:
        return OFFICIAL_BOTH_AVG
    return OFFICIAL_SINGLE_ADJUSTED


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="market-data/working/working_prices.csv")
    parser.add_argument("--output", default="market-data/public/market_prices.csv")
    parser.add_argument("--errors", default="market-data/working/build_public_errors.csv")
    parser.add_argument("--updated-month", default="2026-07")
    parser.add_argument(
        "--data-type-override",
        choices=sorted(ALLOWED_DATA_TYPES),
        default="",
        help="Optional override for manually adjusted or estimated public CSV rows.",
    )
    args = parser.parse_args()

    grouped: dict[tuple[str, str, str], dict[str, dict[str, list[int]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    errors: list[dict[str, str]] = []

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [col for col in WORK_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"missing columns in working CSV: {', '.join(missing)}")
        for line_no, row in enumerate(reader, start=2):
            source = row["source_name"].strip().lower()
            condition = row["condition_label"].strip()
            price_col = CONDITION_TO_PRICE.get(source, {}).get(condition)
            try:
                price = int(str(row["source_price"]).replace(",", ""))
            except ValueError:
                errors.append({"line": str(line_no), "reason": "invalid_source_price", "detail": str(row)})
                continue
            key = (row["instrument_category"].strip(), row["brand_name"].strip(), row["model_name"].strip())
            if not all(key) or not price_col:
                errors.append({"line": str(line_no), "reason": "missing_key_or_unknown_condition", "detail": str(row)})
                continue
            grouped[key][price_col][source].append(price)

    public_rows: list[dict[str, str | int]] = []
    for (category, brand, model), by_condition in sorted(grouped.items()):
        prices: dict[str, int | None] = {}
        price_data_types: dict[str, str | None] = {}
        for col in PRICE_COLUMNS:
            price, data_type = normalized_price(by_condition.get(col, {}))
            prices[col] = price
            price_data_types[col] = data_type
        if any(value is None for value in prices.values()):
            errors.append({"line": "", "reason": "missing_condition_price", "detail": f"{category}/{brand}/{model}: {prices}"})
            continue
        if not (prices["price_good"] >= prices["price_normal"] >= prices["price_used"]):
            errors.append({"line": "", "reason": "unnatural_price_order", "detail": f"{category}/{brand}/{model}: {prices}"})
            continue
        display_name = f"{brand} {model}"
        public_rows.append({
            "instrument_category": category,
            "brand_name": brand,
            "model_name": model,
            "display_name": display_name,
            "price_good": prices["price_good"],
            "price_normal": prices["price_normal"],
            "price_used": prices["price_used"],
            "price_min": prices["price_used"],
            "price_max": prices["price_good"],
            "data_type": args.data_type_override or row_data_type(price_data_types),
            "updated_month": args.updated_month,
            "is_active": "true",
            "brand_aliases": "",
            "model_aliases": "",
            "search_keywords": f"{display_name} {category}",
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=PUBLIC_COLUMNS)
        writer.writeheader()
        writer.writerows(public_rows)

    Path(args.errors).parent.mkdir(parents=True, exist_ok=True)
    with open(args.errors, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["line", "reason", "detail"])
        writer.writeheader()
        writer.writerows(errors)

    print(f"wrote {len(public_rows)} public rows to {args.output}; {len(errors)} errors to {args.errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
