import csv
import io
import re
from dataclasses import dataclass

import httpx

SCIMAGO_URL = "https://www.scimagojr.com/journalrank.php"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Journal:
    issn: str
    title: str
    sjr: float | None
    quartile: str


def looks_like_html(text: str) -> bool:
    sample = text.lstrip("\ufeff").lstrip().lower()
    return sample.startswith("<!doctype") or sample.startswith("<html") or sample.startswith("<head")


def normalize_issn(raw: str) -> str | None:
    token = re.sub(r"[^0-9Xx]", "", raw).upper()
    if len(token) != 8:
        return None
    return f"{token[:4]}-{token[4:]}"


def parse_sjr(value: str) -> float | None:
    text = value.strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _column(fieldnames: list[str], *needles: str) -> str | None:
    for name in fieldnames:
        lowered = name.strip().lower()
        if all(needle in lowered for needle in needles):
            return name
    return None


KEPT_QUARTILES = {"Q1", "Q2"}


def parse_scimago_csv(text: str) -> list[Journal]:
    """Keep journals whose Sports Science quartile is Q1 or Q2, one row per ISSN."""
    cleaned = text.lstrip("\ufeff").strip()
    if not cleaned or looks_like_html(cleaned):
        raise ValueError(
            "SCImago returned a page instead of a CSV. "
            "Save the Sports Science ranking as a CSV and run "
            "python -m literature journals --csv PATH."
        )
    header = cleaned.splitlines()[0]
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    reader = csv.DictReader(io.StringIO(cleaned), delimiter=delimiter)
    if not reader.fieldnames:
        return []
    names = list(reader.fieldnames)
    title_col = _column(names, "title")
    type_col = _column(names, "type")
    issn_col = _column(names, "issn")
    quartile_col = _column(names, "quartile")
    sjr_col = next(
        (name for name in names if name.strip().lower() == "sjr"),
        None,
    )
    if not title_col or not issn_col or not quartile_col:
        raise ValueError("The SCImago CSV is missing a title, ISSN, or quartile column.")

    found: dict[str, Journal] = {}
    for row in reader:
        if type_col and (row.get(type_col) or "").strip().lower() not in {"", "journal"}:
            continue
        quartile = (row.get(quartile_col) or "").strip().upper()
        if quartile not in KEPT_QUARTILES:
            continue
        title = (row.get(title_col) or "").strip()
        if not title:
            continue
        sjr = parse_sjr(row.get(sjr_col) or "") if sjr_col else None
        for piece in re.split(r"[,;]", row.get(issn_col) or ""):
            issn = normalize_issn(piece)
            if issn:
                found[issn] = Journal(issn=issn, title=title, sjr=sjr, quartile=quartile)
    return list(found.values())


def download_scimago(area: str, category: str, client: httpx.Client) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": SCIMAGO_URL,
    }
    client.get(SCIMAGO_URL, headers=headers)
    response = client.get(
        SCIMAGO_URL,
        params={
            "area": area,
            "category": category,
            "country": "all",
            "order": "sjr",
            "min": "0",
            "min_type": "cd",
            "type": "j",
            "out": "xls",
        },
        headers=headers,
    )
    text = response.text
    if response.status_code >= 400 or looks_like_html(text) or not text.strip():
        raise ValueError(
            "SCImago returned a page instead of a CSV. "
            "Save the Sports Science ranking as a CSV and run "
            "python -m literature journals --csv PATH."
        )
    return text
