from __future__ import annotations

import csv
import json
import hashlib
from collections import Counter
from pathlib import Path

from .schema import NORMALIZED_FIELDS


def validate_csv(path: Path) -> dict[str, object]:
    record_ids: set[str] = set()
    source_urls: set[str] = set()
    fingerprints: set[str] = set()
    duplicate_ids = 0
    duplicate_source_urls = 0
    duplicate_fingerprints = 0
    counts = Counter()
    years = Counter()
    currencies = Counter()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != NORMALIZED_FIELDS:
            raise ValueError("Normalized CSV schema does not match the declared schema")
        for row in reader:
            counts["rows"] += 1
            record_id = row["record_id"]
            if record_id in record_ids:
                duplicate_ids += 1
            record_ids.add(record_id)
            source_url = row["source_record_url"]
            if source_url:
                if source_url in source_urls:
                    duplicate_source_urls += 1
                source_urls.add(source_url)
            fingerprint_fields = (
                row["auction_date"], row["artist"], row["title"], row["technique"],
                row["edition"], row["price_text"], row["source_record_url_raw"],
            )
            fingerprint = hashlib.sha256("\x1f".join(fingerprint_fields).encode("utf-8")).hexdigest()
            if fingerprint in fingerprints:
                duplicate_fingerprints += 1
            fingerprints.add(fingerprint)
            if row["price_amount"]:
                counts["parsed_price"] += 1
            if row["source_record_url"]:
                counts["source_url"] += 1
            if row["auction_date"]:
                counts["auction_date"] += 1
                years[row["auction_date"][:4]] += 1
            counts[f"status:{row['sold_status'] or 'blank'}"] += 1
            currencies[row["currency"] or "blank"] += 1

    return {
        "file": str(path),
        "rows": counts["rows"],
        "unique_record_ids": len(record_ids),
        "duplicate_record_ids": duplicate_ids,
        "unique_source_urls": len(source_urls),
        "duplicate_source_url_rows": duplicate_source_urls,
        "unique_lot_fingerprints": len(fingerprints),
        "duplicate_lot_fingerprint_rows": duplicate_fingerprints,
        "rows_with_parsed_price": counts["parsed_price"],
        "rows_with_source_url": counts["source_url"],
        "rows_with_auction_date": counts["auction_date"],
        "sold_status_counts": {
            key.removeprefix("status:"): value
            for key, value in sorted(counts.items())
            if key.startswith("status:")
        },
        "auction_year_counts": dict(sorted(years.items())),
        "currency_counts": dict(sorted(currencies.items())),
    }


def deduplicate_csv(source: Path, destination: Path) -> dict[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    kept = 0
    removed = 0
    with source.open(newline="", encoding="utf-8") as input_handle, destination.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        writer = csv.DictWriter(output_handle, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        for row in reader:
            fingerprint_fields = (
                row["auction_date"], row["artist"], row["title"], row["technique"],
                row["edition"], row["price_text"], row["source_record_url_raw"],
            )
            fingerprint = hashlib.sha256("\x1f".join(fingerprint_fields).encode("utf-8")).hexdigest()
            if fingerprint in seen:
                removed += 1
                continue
            seen.add(fingerprint)
            writer.writerow(row)
            kept += 1
    return {"records_kept": kept, "exact_duplicate_rows_removed": removed}


def latest_observation_per_lot(source: Path, destination: Path) -> dict[str, int]:
    """Keep the latest deposited observation for each source lot URL.

    Repeated lot URLs in the raw deposit can have changing dates and prices. This output
    is deliberately named an observation dataset; it does not assert that the retained
    price is a hammer price or that every lot closed successfully.
    """
    latest: dict[str, dict[str, str]] = {}
    without_url: list[dict[str, str]] = []
    with source.open(newline="", encoding="utf-8") as input_handle:
        reader = csv.DictReader(input_handle)
        for row in reader:
            url = row["source_record_url"]
            if not url:
                without_url.append(row)
                continue
            previous = latest.get(url)
            row_key = (row["auction_date"], int(row["raw_row_number"] or 0))
            previous_key = (
                previous["auction_date"], int(previous["raw_row_number"] or 0)
            ) if previous else ("", -1)
            if previous is None or row_key > previous_key:
                latest[url] = row

    selected = list(latest.values()) + without_url
    selected.sort(key=lambda row: int(row["raw_row_number"] or 0))
    with destination.open("w", newline="", encoding="utf-8") as output_handle:
        writer = csv.DictWriter(output_handle, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        writer.writerows(selected)
    return {
        "records_kept": len(selected),
        "repeated_lot_observations_removed": sum(1 for _ in _iter_rows(source)) - len(selected),
    }


def _iter_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
