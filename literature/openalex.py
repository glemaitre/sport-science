import re
import time
from datetime import datetime, timezone

import httpx

OPENALEX_WORKS = "https://api.openalex.org/works"
SELECT = "id,doi,title,publication_date,authorships,abstract_inverted_index,primary_location"
PAGE_SIZE = 100
ISSN_BATCH = 25
NUMBERED_PAGE_LIMIT = 10000


def reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    positions = [
        position
        for places in inverted.values()
        if isinstance(places, list)
        for position in places
        if isinstance(position, int) and position >= 0
    ]
    if not positions:
        return ""
    words = [""] * (max(positions) + 1)
    for word, places in inverted.items():
        if not isinstance(places, list):
            continue
        for position in places:
            if isinstance(position, int) and 0 <= position < len(words):
                words[position] = str(word)
    return " ".join(word for word in words if word)


def collapse_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def format_authors(authorships: list | None) -> str:
    names: list[str] = []
    for item in authorships or []:
        if not isinstance(item, dict):
            continue
        author = item.get("author") or {}
        name = collapse_space(str(author.get("display_name") or ""))
        if name:
            names.append(name)
    if len(names) > 8:
        return ", ".join(names[:8]) + ", et al."
    return ", ".join(names)


def normalize_doi(value: str | None) -> str:
    doi = collapse_space(value or "")
    if not doi:
        return ""
    if doi.lower().startswith("http://") or doi.lower().startswith("https://"):
        return doi
    return f"https://doi.org/{doi.removeprefix('doi:')}"


def normalize_work(work: dict, fetched_at: str | None = None) -> dict | None:
    openalex_id = collapse_space(str(work.get("id") or ""))
    title = collapse_space(str(work.get("title") or ""))
    if not openalex_id or not title:
        return None
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    source = (work.get("primary_location") or {}).get("source") or {}
    issns = source.get("issn") or []
    journal_issn = ""
    if issns:
        journal_issn = collapse_space(str(issns[0]))
    published_on = collapse_space(str(work.get("publication_date") or ""))
    return {
        "openalex_id": openalex_id,
        "doi": normalize_doi(work.get("doi")),
        "title": title,
        "abstract": abstract,
        "abstract_missing": 0 if abstract else 1,
        "journal_issn": journal_issn,
        "journal_title": collapse_space(str(source.get("display_name") or "")),
        "published_on": published_on,
        "authors": format_authors(work.get("authorships")),
        "fetched_at": fetched_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _chunks(items: list[str], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_works(
    issns: list[str],
    from_date: str,
    mailto: str,
    client: httpx.Client,
    fetch_cap: int,
    to_date: str | None = None,
    api_key: str = "",
) -> tuple[list[dict], bool]:
    """Return normalized works and whether every page in the window was read.

    Without to_date the window stays open, so issues dated ahead of today are included.
    Cursor paging needs an OpenAlex key. Without one, numbered pages reach the first
    10,000 results of a query, which a month of 25 journals stays well under.
    """
    date_filter = f"from_publication_date:{from_date},"
    if to_date:
        date_filter += f"to_publication_date:{to_date},"
    unique = list(dict.fromkeys(issns))
    works: list[dict] = []
    seen: set[str] = set()
    complete = True
    headers = {"User-Agent": f"sport-science-literature/0.1 ({mailto or 'local'})"}
    for batch in _chunks(unique, ISSN_BATCH):
        cursor = "*"
        page = 1
        while True:
            if len(works) >= fetch_cap:
                return works, False
            params = {
                "filter": (
                    f"primary_location.source.issn:{'|'.join(batch)},"
                    f"{date_filter}"
                    "type:article|review"
                ),
                "per-page": str(PAGE_SIZE),
                "select": SELECT,
            }
            if api_key:
                params["api_key"] = api_key
                params["cursor"] = cursor
            else:
                params["page"] = str(page)
            if mailto:
                params["mailto"] = mailto
            response = client.get(OPENALEX_WORKS, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or []
            for item in results:
                normalized = normalize_work(item)
                if normalized is None or normalized["openalex_id"] in seen:
                    continue
                seen.add(normalized["openalex_id"])
                works.append(normalized)
                if len(works) >= fetch_cap:
                    return works, False
            meta = payload.get("meta") or {}
            if api_key:
                next_cursor = meta.get("next_cursor")
                if not results or not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
            else:
                total = int(meta.get("count") or 0)
                if not results or page * PAGE_SIZE >= total:
                    break
                if page * PAGE_SIZE >= NUMBERED_PAGE_LIMIT:
                    complete = False
                    break
                page += 1
            time.sleep(0.1)
    return works, complete
