from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from openpyxl import load_workbook

from .schema import NORMALIZED_FIELDS

DATAVERSE_FILE_URL = "https://repod.icm.edu.pl/api/access/datafile/{file_id}"


def file_md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - verification against publisher metadata
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_repod(config: dict[str, Any], raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    destination = raw_dir / config["filename"]
    expected_md5 = config["md5"].lower()
    if destination.exists() and file_md5(destination) == expected_md5:
        return destination

    url = DATAVERSE_FILE_URL.format(file_id=config["file_id"])
    params = {"format": config["format"]} if config.get("format") else None
    with requests.get(url, params=params, timeout=120, stream=True) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for block in response.iter_content(chunk_size=1024 * 1024):
                if block:
                    handle.write(block)

    actual_md5 = file_md5(destination)
    if actual_md5 != expected_md5:
        destination.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch: expected {expected_md5}, received {actual_md5}")
    return destination


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _source_url(value: Any) -> tuple[str, str]:
    raw = _clean(value)
    if re.match(r"^https?://", raw, re.I):
        return raw, raw
    numeric = re.fullmatch(r"(\d+)(?:\.0)?", raw)
    if numeric:
        # The deposited workbook stores many Catawiki lot URLs as their numeric lot ID.
        return f"https://www.catawiki.com/en/l/{numeric.group(1)}", raw
    return "", raw


def _parse_date(value: Any) -> tuple[str, str]:
    raw = _clean(value)
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat(), raw
    for pattern in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat(), raw
        except ValueError:
            pass
    return "", raw


def _parse_price(value: Any) -> tuple[str, str]:
    text = _clean(value)
    if not text:
        return "", ""
    currency = ""
    currency_match = re.search(r"\b(EUR|USD|GBP|PLN|CHF|JPY|AUD|CAD)\b|[€$£]", text, re.I)
    if currency_match:
        token = currency_match.group(0).upper()
        currency = {"€": "EUR", "$": "USD", "£": "GBP"}.get(token, token)
    numeric = re.search(r"[-+]?\d[\d\s.,]*", text)
    if not numeric:
        return "", currency
    token = numeric.group(0).replace(" ", "")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        tail = token.rsplit(",", 1)[1]
        token = token.replace(",", ".") if len(tail) <= 2 else token.replace(",", "")
    try:
        return f"{float(token):.2f}", currency
    except ValueError:
        return "", currency


def _header_map(headers: Iterable[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, value in enumerate(headers):
        key = re.sub(r"[^A-Z0-9]+", "_", _clean(value).upper()).strip("_")
        if key:
            result[key] = index
    return result


def _pick(row: tuple[Any, ...], header: dict[str, int], *names: str) -> Any:
    for name in names:
        if name in header and header[name] < len(row):
            return row[header[name]]
    return None


def normalize_repod(workbook_path: Path, output_csv: Path, config: dict[str, Any]) -> dict[str, Any]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows)
    header = _header_map(headers)

    required_any = {"ARTIST", "TECHNIQUE", "PRICE"}
    missing = sorted(required_any - set(header))
    if missing:
        raise ValueError(f"Workbook missing required columns: {', '.join(missing)}")

    written = 0
    missing_price = 0
    missing_url = 0
    dataset_currency = _clean(config.get("price_currency")).upper()
    if not re.fullmatch(r"[A-Z]{3}", dataset_currency):
        raise ValueError("RepOD price_currency must be a three-letter ISO currency code")
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        for row_number, row in enumerate(rows, start=2):
            artist = _clean(_pick(row, header, "ARTIST"))
            technique = _clean(_pick(row, header, "TECHNIQUE"))
            price_text = _clean(_pick(row, header, "PRICE"))
            source_url, source_url_raw = _source_url(_pick(row, header, "URL"))
            if not any((artist, technique, price_text, source_url_raw)):
                continue
            price_amount, explicit_currency = _parse_price(price_text)
            if not explicit_currency:
                _, explicit_currency = _parse_price(_pick(row, header, "ESTIMATION", "ESTIMATE"))
            if explicit_currency and explicit_currency != dataset_currency:
                raise ValueError(
                    f"Row {row_number} declares {explicit_currency}, conflicting with "
                    f"the dataset currency {dataset_currency}"
                )
            auction_date, auction_date_raw = _parse_date(_pick(row, header, "AUCTION_DATE"))
            if not price_amount:
                missing_price += 1
            if not source_url:
                missing_url += 1
            record_id = f"repod:{config['dataset_doi']}:{row_number}"
            normalized = {field: "" for field in NORMALIZED_FIELDS}
            normalized.update(
                {
                    "record_id": record_id,
                    "source_name": "RepOD: Art auction result of prints",
                    "source_dataset_doi": config["dataset_doi"],
                    "source_record_url": source_url,
                    "source_record_url_raw": source_url_raw,
                    "source_file": workbook_path.name,
                    "retrieved_at_utc": retrieved,
                    "auction_date": auction_date,
                    "auction_date_raw": auction_date_raw,
                    "artist": artist,
                    "title": _clean(_pick(row, header, "TITLE_OF_ARTWORK", "TITLE")),
                    "object_type": _clean(_pick(row, header, "OBJECT")),
                    "technique": technique,
                    "signature": _clean(_pick(row, header, "SIGNATURE")),
                    "edition": _clean(_pick(row, header, "EDITION")),
                    "condition": _clean(_pick(row, header, "CONDITION")),
                    "dimensions_text": _clean(_pick(row, header, "TOTAL_DIMENSIONS")),
                    "creation_year": _clean(_pick(row, header, "YEAR")),
                    "estimate_text": _clean(_pick(row, header, "ESTIMATION", "ESTIMATE")),
                    "price_text": price_text,
                    "price_amount": price_amount,
                    # Currency is supplied by dataset-level metadata in the associated
                    # article. The authors' preprocessing code does not convert PRICE.
                    "currency": dataset_currency,
                    "currency_raw": "",
                    "sold_status": "reported_sold" if price_amount else "unknown",
                    "sale_format": "online-only" if "catawiki.com" in source_url else "",
                    "auction_house": "Catawiki" if "catawiki.com" in source_url else "",
                    "raw_row_number": str(row_number),
                }
            )
            writer.writerow(normalized)
            written += 1
    workbook.close()
    return {
        "records_written": written,
        "records_missing_parsed_price": missing_price,
        "records_missing_source_url": missing_url,
        "price_currency": dataset_currency,
        "currency_assignment_basis": config["currency_basis"],
        "associated_article_url": config["associated_article_url"],
        "preprocessing_code_url": config["preprocessing_code_url"],
        "headers": list(header),
        "source_md5": file_md5(workbook_path),
        "output": str(output_csv),
    }


def load_sources(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count_tabular_rows(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        reader = csv.reader(handle, dialect)
        headers = next(reader)
        rows = sum(1 for _ in reader)
    return {"file": str(path), "rows": rows, "headers": headers, "md5": file_md5(path)}
