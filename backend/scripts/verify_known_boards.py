"""Check every entry of the bundled known-board list against the live public board APIs.

Each board in ``app/data/known_boards.json`` is fetched once through its board adapter
(``count_board_jobs`` - the same verification ``PUT /companies/{id}/board`` and board
auto-detection use) and must have at least one open job. Prints a table and a summary.

Usage::

    cd backend
    ./.venv/Scripts/python.exe scripts/verify_known_boards.py                 # report only
    ./.venv/Scripts/python.exe scripts/verify_known_boards.py --remove-failed # also drop failures from the file

Only the four vendors' public, unauthenticated JSON APIs are called, with JobPilot's
descriptive User-Agent, a few requests in parallel at most. A board that cannot be reached
(network error, 5xx) is reported as UNREACHABLE and never removed - only boards the vendor
says do not exist (404), answer with something that is not a board, or have no open jobs.

Exit code: 0 when every board verified, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# Allow "python scripts/verify_known_boards.py" from anywhere in the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.adapters.boards.http import BoardFetchError, BoardNotFound, BoardPayloadError  # noqa: E402
from app.modules.adapters.registry import get_adapter  # noqa: E402
from app.modules.companies.board_detect import KNOWN_BOARDS_FILE, KnownBoard, known_boards  # noqa: E402


@dataclass
class Check:
    board: KnownBoard
    status: str  # OK | EMPTY | NOT_FOUND | BAD_PAYLOAD | UNREACHABLE
    open_jobs: int | None = None
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.status in ("EMPTY", "NOT_FOUND", "BAD_PAYLOAD")


def check(board: KnownBoard, pause: float) -> Check:
    time.sleep(pause)  # spread the requests out a little
    try:
        count = int(get_adapter(board.ats_type).count_board_jobs(board.token))
    except BoardNotFound as exc:
        return Check(board, "NOT_FOUND", detail=str(exc))
    except BoardPayloadError as exc:
        return Check(board, "BAD_PAYLOAD", detail=str(exc))
    except BoardFetchError as exc:
        return Check(board, "UNREACHABLE", detail=str(exc))
    return Check(board, "OK" if count > 0 else "EMPTY", open_jobs=count)


def write_without(failed: set[tuple[str, str]]) -> int:
    """Rewrite the JSON file without the failed ``(ats_type, token)`` boards; one board per line."""
    data = json.loads(KNOWN_BOARDS_FILE.read_text(encoding="utf-8"))
    boards = data.get("boards") or []
    kept = [b for b in boards if (str(b.get("ats_type")).upper(), str(b.get("token"))) not in failed]
    lines = ["{"]
    for key, value in data.items():
        if key != "boards":
            lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    lines.append('  "boards": [')
    for i, board in enumerate(kept):
        lines.append("    " + json.dumps(board, ensure_ascii=False) + ("," if i < len(kept) - 1 else ""))
    lines += ["  ]", "}", ""]
    KNOWN_BOARDS_FILE.write_text("\n".join(lines), encoding="utf-8")
    return len(boards) - len(kept)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workers", type=int, default=4, help="boards checked in parallel (default 4)")
    parser.add_argument("--remove-failed", action="store_true", help="drop boards that failed from the JSON file")
    args = parser.parse_args(argv)

    boards = known_boards()
    workers = max(1, min(args.workers, 8))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda b: check(b, 0.25), boards))

    width = max((len(r.board.name) for r in results), default=10)
    print(f"{'Company':<{width}}  {'ATS':<16} {'Token':<22} {'Open jobs':>9}  Status")
    print("-" * (width + 60))
    for r in sorted(results, key=lambda r: (r.status != "OK", r.board.name.lower())):
        jobs = "" if r.open_jobs is None else str(r.open_jobs)
        print(f"{r.board.name:<{width}}  {r.board.ats_type.value:<16} {r.board.token:<22} {jobs:>9}  {r.status}")

    ok = [r for r in results if r.status == "OK"]
    failed = [r for r in results if r.failed]
    unreachable = [r for r in results if r.status == "UNREACHABLE"]
    by_vendor: dict[str, int] = {}
    for r in ok:
        by_vendor[r.board.ats_type.value] = by_vendor.get(r.board.ats_type.value, 0) + 1
    print()
    print(
        f"{len(results)} boards: {len(ok)} verified, {len(failed)} failed, {len(unreachable)} unreachable "
        f"({', '.join(f'{v} {n}' for v, n in sorted(by_vendor.items()))})"
    )
    for r in failed + unreachable:
        print(f"  {r.status:<12} {r.board.name} ({r.board.ats_type.value}/{r.board.token}) {r.detail}")
    if args.remove_failed and failed:
        removed = write_without({(r.board.ats_type.value, r.board.token) for r in failed})
        print(f"Removed {removed} failed boards from {KNOWN_BOARDS_FILE}")
    return 0 if not failed and not unreachable else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
