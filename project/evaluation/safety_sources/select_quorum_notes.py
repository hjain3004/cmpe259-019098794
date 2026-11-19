"""Deterministically select and adapt red-team attack notes from Quorum.

    cd project
    python evaluation/safety_sources/select_quorum_notes.py /tmp/quorum-drexathon-2026/results/arena/attacks.jsonl

Writes evaluation/safety_sources/quorum_notes.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
IBAN_RE = re.compile(r"GB\d\d(?: ?\d{4}){5}")
MAX_NOTE_LEN = 400


def forbidden_last4s(vendor_history_path: Path) -> set[str]:
    vh = json.loads(vendor_history_path.read_text())
    out = set()
    for v in vh:
        vp = v.get("verified_payment") or {}
        if vp.get("account_number"):
            out.add(vp["account_number"][-4:])
    return out


def fake_us_pair(index: int, forbidden: set[str]) -> tuple[str, str]:
    """Return a deterministic fake (account, routing) pair whose last4 is not in forbidden."""
    n = 6101 + index
    while f"{n:04d}" in forbidden:
        n += 100
    account = f"007100{n:04d}"
    routing = f"021000{701 + index:03d}"
    return account, routing


def adapt_note(text: str, account: str, routing: str) -> tuple[str | None, str | None]:
    """Replace UK IBANs with fake US account/routing numbers; skip if no IBAN or > 400 chars."""
    if not IBAN_RE.search(text):
        return None, "no_iban"
    adapted = IBAN_RE.sub(f"account {account}, routing {routing}", text)
    if len(adapted) > MAX_NOTE_LEN:
        return None, f"over_{MAX_NOTE_LEN}_chars({len(adapted)})"
    return adapted, None


def select_family(
    rows: list[dict],
    family: str,
    limit: int,
    forbidden: set[str],
    start_index: int = 0,
) -> tuple[list[dict], list[dict]]:
    groups: dict[tuple[str, ...], list[dict]] = {}
    for r in rows:
        key = tuple(r["note"].lower().split()[:4])
        groups.setdefault(key, []).append(r)

    skipped: list[dict] = []
    candidates: list[dict] = []
    # Sort each group by (risk_score, id) and pick the best adaptable member.
    for _, members in sorted(groups.items(), key=lambda kv: min((m["decisions"]["drex"]["risk_score"], m["id"]) for m in kv[1])):
        members_sorted = sorted(members, key=lambda m: (m["decisions"]["drex"]["risk_score"], m["id"]))
        for m in members_sorted:
            # Probe adaptation with a placeholder pair of the exact same length to check length & IBAN presence.
            probe_acct, probe_rout = fake_us_pair(start_index + len(candidates), forbidden)
            adapted, reason = adapt_note(m["note"], probe_acct, probe_rout)
            if adapted is None:
                skipped.append({"quorum_id": m["id"], "family": family, "reason": reason})
                continue
            candidates.append({
                "quorum_id": m["id"],
                "family": family,
                "original_text": m["note"],
                "adapted_text": adapted,
                "account": probe_acct,
                "routing": probe_rout,
                "last4": probe_acct[-4:],
                "drex_final_action": m["decisions"]["drex"]["final_action"],
                "drex_risk_score": m["decisions"]["drex"]["risk_score"],
            })
            break

    candidates.sort(key=lambda c: (c["drex_risk_score"], c["quorum_id"]))
    selected = candidates[:limit]
    # Re-assign sequential fake US pairs in final selected order so indices are contiguous.
    for i, item in enumerate(selected):
        acct, rout = fake_us_pair(start_index + i, forbidden)
        adapted, _ = adapt_note(item["original_text"], acct, rout)
        item["account"] = acct
        item["routing"] = rout
        item["last4"] = acct[-4:]
        item["adapted_text"] = adapted
    return selected, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("attacks_jsonl", type=Path)
    ap.add_argument("--out", type=Path, default=PROJECT / "evaluation" / "safety_sources" / "quorum_notes.json")
    a = ap.parse_args(argv)

    rows = [json.loads(line) for line in a.attacks_jsonl.read_text().splitlines() if line.strip()]
    forbidden = forbidden_last4s(PROJECT / "data" / "dev" / "cafe_01" / "vendor_history.json")

    redirect_rows = [
        r for r in rows
        if r.get("kind") == "poisoned" and r.get("decisions", {}).get("drex", {}).get("final_action") == "approve"
    ]
    swap_rows = [r for r in rows if r.get("kind") == "forged"]

    redirects, skip_r = select_family(redirect_rows, "redirect", 8, forbidden, start_index=0)
    swaps, skip_s = select_family(swap_rows, "swap", 4, forbidden, start_index=len(redirects))

    out_data = {
        "source": "quorum-drexathon-2026/results/arena/attacks.jsonl",
        "notes": redirects + swaps,
        "skipped": skip_r + skip_s,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out_data, indent=2) + "\n")
    print(f"wrote {a.out}: {len(redirects)} redirect, {len(swaps)} swap, {len(skip_r) + len(skip_s)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
