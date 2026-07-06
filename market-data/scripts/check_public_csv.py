#!/usr/bin/env python3
"""Quality checks for the public simulator CSV."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

PUBLIC_COLUMNS = ["instrument_category","brand_name","model_name","display_name","price_good","price_normal","price_used","price_min","price_max","data_type","updated_month","is_active","brand_aliases","model_aliases","search_keywords"]
TARGET_COUNTS = {"エレキギター": 200, "アコースティックギター": 150, "ベース": 120, "サックス": 60, "電子ピアノ": 40, "フルート": 40, "クラリネット": 40}
PRICE_COLUMNS = ["price_good", "price_normal", "price_used", "price_min", "price_max"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="market-data/public/market_prices.csv")
    parser.add_argument("--report", default="market-data/public/quality_report.csv")
    parser.add_argument("--updated-month", default="2026-07")
    args = parser.parse_args()

    errors: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    keys: Counter[tuple[str, str, str]] = Counter()

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [col for col in PUBLIC_COLUMNS if col not in (reader.fieldnames or [])]
        extra = [col for col in (reader.fieldnames or []) if col not in PUBLIC_COLUMNS]
        if missing:
            errors.append({"line": "1", "severity": "error", "reason": "missing_columns", "detail": ",".join(missing)})
        if extra:
            errors.append({"line": "1", "severity": "warning", "reason": "extra_columns", "detail": ",".join(extra)})

        for line_no, row in enumerate(reader, start=2):
            for col in PUBLIC_COLUMNS:
                if col not in row:
                    continue
                if col not in {"brand_aliases", "model_aliases"} and not str(row[col]).strip():
                    errors.append({"line": str(line_no), "severity": "error", "reason": "blank_required_value", "detail": col})
            prices: dict[str, int] = {}
            for col in PRICE_COLUMNS:
                try:
                    prices[col] = int(str(row[col]).replace(",", ""))
                except (ValueError, TypeError):
                    errors.append({"line": str(line_no), "severity": "error", "reason": "invalid_price", "detail": col})
            if len(prices) == len(PRICE_COLUMNS):
                if not (prices["price_good"] >= prices["price_normal"] >= prices["price_used"]):
                    errors.append({"line": str(line_no), "severity": "error", "reason": "unnatural_price_order", "detail": str(prices)})
                if prices["price_min"] != prices["price_used"] or prices["price_max"] != prices["price_good"]:
                    errors.append({"line": str(line_no), "severity": "error", "reason": "min_max_mismatch", "detail": str(prices)})
                if any(value % 1000 != 0 for value in prices.values()):
                    errors.append({"line": str(line_no), "severity": "error", "reason": "price_not_rounded_to_1000", "detail": str(prices)})
            if row.get("updated_month") != args.updated_month:
                errors.append({"line": str(line_no), "severity": "error", "reason": "updated_month_mismatch", "detail": row.get("updated_month", "")})
            if row.get("is_active") != "true":
                errors.append({"line": str(line_no), "severity": "error", "reason": "is_active_not_true", "detail": row.get("is_active", "")})
            key = (row.get("instrument_category", ""), row.get("brand_name", ""), row.get("model_name", ""))
            keys[key] += 1
            counts[row.get("instrument_category", "")] += 1

    for key, count in keys.items():
        if count > 1:
            errors.append({"line": "", "severity": "error", "reason": "duplicate_item", "detail": f"{key}: {count}"})
    for category, target in TARGET_COUNTS.items():
        actual = counts.get(category, 0)
        if actual < target:
            errors.append({"line": "", "severity": "warning", "reason": "below_target_count", "detail": f"{category}: {actual}/{target}"})

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["line", "severity", "reason", "detail"])
        writer.writeheader()
        writer.writerows(errors)

    error_count = sum(1 for item in errors if item["severity"] == "error")
    warning_count = sum(1 for item in errors if item["severity"] == "warning")
    print(f"checked {sum(counts.values())} rows; {error_count} errors, {warning_count} warnings; report: {args.report}")
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
