import sys

from dotenv import load_dotenv

from literature.config import ROOT
from literature.run import refresh_journals, run_literature


def main(argv: list[str]) -> int:
    load_dotenv(ROOT / ".env")
    if not argv:
        return run_literature()
    if argv[0] != "journals":
        print("Usage: python -m literature [journals [--csv PATH]]", file=sys.stderr)
        return 2
    if len(argv) == 1:
        return refresh_journals()
    if len(argv) == 3 and argv[1] == "--csv":
        return refresh_journals(argv[2])
    print("Usage: python -m literature journals [--csv PATH]", file=sys.stderr)
    return 2
