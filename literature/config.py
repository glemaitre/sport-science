import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
DB_PATH = PACKAGE / "data" / "literature.sqlite"
WEB_DIR = PACKAGE / "web"
PAPERS_JS = WEB_DIR / "papers.js"
INTEREST_BRIEF = PACKAGE / "interest_brief.md"


@dataclass(frozen=True)
class Config:
    model: str
    start_date: str
    overlap_days: int
    keep_threshold: int
    max_papers: int
    scimago_area: str
    scimago_category: str
    screen_batch: int = 8
    note_batch: int = 4
    fetch_cap: int = 10000


def load_config() -> Config:
    data = tomllib.loads((PACKAGE / "config.toml").read_text(encoding="utf-8"))
    model = os.environ.get("OPENROUTER_MODEL", "").strip() or data["model"]
    start_date = date.fromisoformat(str(data["start_date"])).isoformat()
    return Config(
        model=model,
        start_date=start_date,
        overlap_days=int(data["overlap_days"]),
        keep_threshold=int(data["keep_threshold"]),
        max_papers=int(data["max_papers"]),
        scimago_area=str(data["scimago_area"]),
        scimago_category=str(data["scimago_category"]),
        fetch_cap=int(data.get("fetch_cap", 10000)),
    )


def openalex_mailto() -> str:
    return os.environ.get("OPENALEX_MAILTO", "").strip()


def openalex_key() -> str:
    return os.environ.get("OPENALEX_API_KEY", "").strip()


def openrouter_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()
