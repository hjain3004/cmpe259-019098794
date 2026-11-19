"""Extract unseen test questions from saved classmate demo sessions.

    cd project
    python evaluation/peer_queries.py
    python evaluation/peer_queries.py --sessions demo/sessions --out evaluation/peer_queries_draft.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.evaluation import QuerySuite

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS = PROJECT / "demo" / "sessions"
DEFAULT_QUERIES = PROJECT / "evaluation" / "queries.yaml"
DEFAULT_OUT = PROJECT / "evaluation" / "peer_queries_draft.yaml"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def load_known_questions(queries_path: Path = DEFAULT_QUERIES) -> set[str]:
    suite = QuerySuite.model_validate(yaml.safe_load(queries_path.read_text(encoding="utf-8")))
    return {_norm(t.text) for conv in suite.conversations for t in conv.turns}


def extract_unseen_queries(
    sessions_dir: Path = DEFAULT_SESSIONS,
    queries_path: Path = DEFAULT_QUERIES,
) -> list[dict[str, Any]]:
    known = load_known_questions(queries_path)
    seen: set[str] = set()
    drafts: list[dict[str, Any]] = []

    for path in sorted(sessions_dir.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                q = str(rec.get("question") or "").strip()
                nq = _norm(q)
                if not nq or nq in known or nq in seen:
                    continue
                seen.add(nq)
                drafts.append({
                    "id": f"PQ{len(drafts) + 1:02d}",
                    "question": q,
                    "tester": rec.get("tester", "anonymous"),
                    "config_seen": rec.get("config", ""),
                    "model_answerability": rec.get("answerability"),
                    "expected_answerability": "",
                    "expected_behavior": "",
                    "notes": "",
                })
    return drafts


def write_peer_queries_draft(
    sessions_dir: Path = DEFAULT_SESSIONS,
    queries_path: Path = DEFAULT_QUERIES,
    out_path: Path = DEFAULT_OUT,
) -> list[dict[str, Any]]:
    drafts = extract_unseen_queries(sessions_dir=sessions_dir, queries_path=queries_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source_dir": str(sessions_dir), "count": len(drafts), "questions": drafts}
    out_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return drafts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    ap.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()

    drafts = write_peer_queries_draft(a.sessions, a.queries, a.out)
    print(f"extracted {len(drafts)} unseen questions -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
