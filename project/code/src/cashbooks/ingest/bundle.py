"""Readers for the non-PDF files in a scenario bundle."""

from __future__ import annotations

import json
from pathlib import Path


def read_messages(path: str | Path) -> list[dict]:
    """messages.jsonl -> list of dicts (msg_id, received_on, channel, from, subject, body)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def read_vendor_history(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_ledger(bundle_dir: str | Path) -> dict:
    with open(Path(bundle_dir) / "ledger.json", encoding="utf-8") as f:
        return json.load(f)


def read_fields_manifest(pdf_path: str | Path) -> dict:
    """The renderer's record of exactly what it printed for each field."""
    p = Path(pdf_path)
    with open(p.with_suffix(".fields.json"), encoding="utf-8") as f:
        return json.load(f)
