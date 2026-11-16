import hashlib
import json
import re
import time

import httpx

from literature.config import INTEREST_BRIEF, Config

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
KINDS = {"cycling", "endurance", "physiology"}
ABSTRACT_LIMIT = 1500

SCREEN_SYSTEM = """You screen new papers for a data scientist at a professional cycling team.

Keep a paper when it helps the team understand, analyse, interpret, or improve cycling performance. That includes physiology, nutrition, biomechanics, aerodynamics, and neighbouring work on training, recovery, heat, altitude, pacing, monitoring, and testing.

Physiology, including fuel use, is not limited to cycling. Keep a finding from running, trail running, rowing, swimming, triathlon, cross-country skiing, or race walking when the mechanism would transfer to the bike. Biomechanics and aerodynamics count when the task is cycling, or when the method applies directly to the bike. Do not keep a running-gait or team-sport movement paper only because the athletes are fit.

Drop surgery technique, sport management, match analysis, talent identification, coaching pedagogy, and rehab protocols that do not teach a performance mechanism. Drop intermittent team sports unless the finding is a mechanism that would transfer.

Score relevance from 0 to 10. 6 is the keep cutoff.
- 8 to 10: a direct finding on cycling performance: physiology, nutrition, biomechanics, aerodynamics, pacing, or testing in cyclists or on the bike.
- 6 to 7: a finding in another continuous endurance sport, or a mechanism studied without a sport, that clearly transfers to endurance performance on the bike.
- 5 or below: general exercise science with no endurance link. That includes resistance or strength training, body composition and weight loss, team sports such as football, rugby, or ice hockey, sport psychology and motivation, coaching, and general health or clinical populations. Score these 5 or below even when the physiology is sound.
- 0: unrelated.

kind is cycling when the subjects or the task are cycling, endurance when they do another continuous endurance sport, and physiology when the paper is about a mechanism relevant to endurance performance and names no sport. Nutrition, biomechanics, and aerodynamics of cycling are kind cycling. Use an empty kind when the paper scores 5 or below.
sport is the sport studied, or an empty string when there is no sport.
why is one sentence on why the paper is here, or why it was dropped. Do not copy the abstract.

Return JSON only, as {"papers": [{"id", "score", "keep", "kind", "sport", "why"}]}. keep is true when the score is 6 or above. Use the ids you were given."""


def note_system(brief: str) -> str:
    return f"""You write a short note for a data scientist at a professional cycling team. Plain language. Do not invent a number that is not in the abstract. Do not copy the abstract. Name the sport the subjects actually did. Say what the team could use, and what would transfer to the bike when the subjects were not cyclists.

learn is two or three sentences.

Return JSON only, as {{"papers": [{{"id", "learn"}}]}}. Use the ids you were given.

Interest profile:
{brief}"""


def _version(*parts: str) -> str:
    digest = hashlib.sha256("\n\x00\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def read_brief() -> str:
    return INTEREST_BRIEF.read_text(encoding="utf-8")


def screen_version(model: str, brief: str | None = None) -> str:
    return _version(SCREEN_SYSTEM, read_brief() if brief is None else brief, model)


def note_version(model: str, brief: str | None = None) -> str:
    text = read_brief() if brief is None else brief
    return _version(note_system(text), text, model)


def extract_json(text: str):
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def paper_entries(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("papers", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if "id" in payload:
            return [payload]
    raise ValueError("The model response had no papers.")


def message_text(payload: dict) -> str:
    content = payload["choices"][0]["message"].get("content") or ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


def clamp_score(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(10, score))


def clean_kind(value) -> str:
    kind = str(value or "").strip().lower()
    return kind if kind in KINDS else ""


def clean_sport(value) -> str:
    sport = re.sub(r"\s+", " ", str(value or "")).strip()
    if sport.lower() in {"", "none", "n/a", "na"}:
        return ""
    return sport[:80]


def screen_records(payload) -> dict[str, dict]:
    records = {}
    for item in paper_entries(payload):
        paper_id = str(item.get("id") or "").strip()
        score = clamp_score(item.get("score"))
        if not paper_id or score is None:
            continue
        records[paper_id] = {
            "score": score,
            "kind": clean_kind(item.get("kind")),
            "sport": clean_sport(item.get("sport")),
            "why": re.sub(r"\s+", " ", str(item.get("why") or "")).strip(),
        }
    return records


def note_records(payload) -> dict[str, dict]:
    records = {}
    for item in paper_entries(payload):
        paper_id = str(item.get("id") or "").strip()
        learn = re.sub(r"\s+", " ", str(item.get("learn") or "")).strip()
        if not paper_id or not learn:
            continue
        records[paper_id] = {"learn": learn}
    return records


def paper_for_model(row, limit: int = ABSTRACT_LIMIT) -> dict:
    abstract = (row["abstract"] or "").strip()
    if len(abstract) > limit:
        abstract = abstract[:limit].rstrip() + "…"
    if row["abstract_missing"] or not abstract:
        abstract = ""
    return {
        "id": row["openalex_id"],
        "title": row["title"],
        "journal": row["journal_title"] or "",
        "abstract": abstract or "The abstract was missing. Judge the title only.",
    }


def post_chat(client: httpx.Client, key: str, model: str, system: str, user: str) -> dict:
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glemaitre.github.io/sport-science/",
        "X-Title": "Sport science literature",
    }
    for attempt in range(3):
        response = client.post(OPENROUTER_URL, headers=headers, json=body)
        if response.status_code == 429 and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        if response.status_code == 400 and "response_format" in body:
            body = {key_name: value for key_name, value in body.items() if key_name != "response_format"}
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()
    return response.json()


def complete_json(client: httpx.Client, key: str, model: str, system: str, user: str):
    last_error: Exception | None = None
    for _ in range(2):
        try:
            payload = post_chat(client, key, model, system, user)
            return extract_json(message_text(payload))
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def screen_papers(client: httpx.Client, key: str, config: Config, rows) -> dict[str, dict]:
    user = json.dumps([paper_for_model(row) for row in rows], ensure_ascii=True)
    payload = complete_json(client, key, config.model, SCREEN_SYSTEM, user)
    return screen_records(payload)


def write_notes(client: httpx.Client, key: str, config: Config, rows) -> dict[str, dict]:
    brief = read_brief()
    papers = []
    for row in rows:
        item = paper_for_model(row, limit=2000)
        item["score"] = row["score"]
        item["why"] = row["why"] or ""
        papers.append(item)
    user = json.dumps(papers, ensure_ascii=True)
    payload = complete_json(client, key, config.model, note_system(brief), user)
    return note_records(payload)
