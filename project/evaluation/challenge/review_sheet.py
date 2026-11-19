"""Generate a self-contained HTML human review sheet for a challenge run folder.

    cd project
    ../.venv/bin/python evaluation/challenge/review_sheet.py evaluation/results/challenge/<run>

Writes <run_folder>/review.html with per-turn details, masked tool calls, 0/1/2 rubric
selectors, notes boxes, and a vanilla-JS "Export CSV" button saving human_scores.csv.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from cashbooks.contracts.postprocess import mask_numbers

PROJECT = Path(__file__).resolve().parents[2]
CHALLENGE_DIR = Path(__file__).resolve().parent
_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)
_SENSITIVE_KEY = re.compile(r"(account|routing|acct|iban|card)", re.I)


def mask_sensitive_value(key: str, value: Any) -> str:
    """Render a scalar/object value with account-like fields masked to the last 4 digits."""
    if value is None:
        return "null"
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    text = mask_numbers(text)
    if _SENSITIVE_KEY.search(key):
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 4:
            return f"****{digits[-4:]}"
        alnum = re.sub(r"[^A-Za-z0-9]", "", text)
        if len(alnum) > 4:
            return f"****{alnum[-4:]}"
    return text


def format_tool_calls(tool_calls: list[dict[str, Any]], max_arg_len: int = 80) -> list[str]:
    """Return concise single-line descriptions of tool calls with masked account args."""
    rendered: list[str] = []
    for tc in tool_calls:
        name = str(tc.get("name") or tc.get("tool") or "unknown_tool")
        args = tc.get("args") if isinstance(tc.get("args"), dict) else tc.get("arguments")
        if isinstance(args, dict) and args:
            parts: list[str] = []
            for k, v in args.items():
                val_str = mask_sensitive_value(str(k), v)
                if len(val_str) > max_arg_len:
                    val_str = val_str[: max_arg_len - 3] + "..."
                parts.append(f"{k}={val_str}")
            rendered.append(f"{name}({', '.join(parts)})")
        else:
            rendered.append(f"{name}()")
    return rendered


def extract_tool_calls(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize tool call records from `tool_calls` or `context` in a log row."""
    raw_calls = row.get("tool_calls")
    if isinstance(raw_calls, list) and raw_calls:
        out: list[dict[str, Any]] = []
        for c in raw_calls:
            if isinstance(c, dict):
                out.append(
                    {
                        "name": str(c.get("tool") or c.get("name") or ""),
                        "args": c.get("args") if isinstance(c.get("args"), dict) else (c.get("arguments") or {}),
                        "result": c.get("result", ""),
                    }
                )
        return out

    ctx = row.get("context") or []
    out = []
    if isinstance(ctx, list):
        for c in ctx:
            if isinstance(c, dict) and ("tool" in c or "name" in c):
                out.append(
                    {
                        "name": str(c.get("tool") or c.get("name") or ""),
                        "args": c.get("args") if isinstance(c.get("args"), dict) else (c.get("arguments") or {}),
                        "result": c.get("result", ""),
                    }
                )
    return out


def load_log_rows(run_folder: Path) -> list[dict[str, Any]]:
    """Read log.jsonl into raw normalized dictionaries without failing on challenge extensions."""
    log_path = run_folder / "log.jsonl"
    if not log_path.exists():
        raise FileNotFoundError(f"missing log.jsonl in {run_folder}")
    rows: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def load_summary(run_folder: Path) -> dict[str, Any]:
    path = run_folder / "summary.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _resolve_candidate_path(raw_path: str | Path | None, run_folder: Path) -> Path | None:
    if not raw_path:
        return None
    p = Path(raw_path)
    if p.exists():
        return p
    for base in (run_folder, PROJECT, CHALLENGE_DIR):
        cand = base / p
        if cand.exists():
            return cand
    return None


def _as_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val if x is not None and str(x).strip()]
    s = str(val).strip()
    return [s] if s else []


def _merge_turn_meta(dst: dict[str, Any], src: dict[str, Any]) -> None:
    if not isinstance(src, dict):
        return
    allowed = src.get("allowed") or src.get("allowed_types") or src.get("expected_types")
    if allowed:
        dst["allowed_types"] = [x.upper() for x in _as_list(allowed)]
    elif src.get("expected") and not dst.get("allowed_types"):
        dst["allowed_types"] = [str(src["expected"]).upper()]

    req_vals = src.get("required_values") or src.get("values") or src.get("gold_values")
    if isinstance(req_vals, dict) and req_vals:
        merged = dict(dst.get("required_values") or {})
        merged.update(req_vals)
        dst["required_values"] = merged

    rubric = src.get("rubric") or src.get("rubric_criteria")
    if rubric:
        dst["rubric"] = rubric

    tools = src.get("expected_tools") or src.get("tools") or src.get("required_tools")
    if tools:
        dst["expected_tools"] = _as_list(tools)

    if src.get("expected_behavior") and not dst.get("expected_behavior"):
        dst["expected_behavior"] = str(src["expected_behavior"])
    if src.get("evidence") and not dst.get("evidence"):
        dst["evidence"] = list(src["evidence"])
    if "scored" in src:
        dst["scored"] = bool(src["scored"])


def load_challenge_metadata(
    run_folder: Path,
    gold_path: Path | None = None,
    queries_path: Path | None = None,
) -> tuple[dict[tuple[str, int], dict[str, Any]], Path | None]:
    """Load per-(query_id, turn_index) gold & query specs plus detected bundle path."""
    summary = load_summary(run_folder)
    bundle_dir = _resolve_candidate_path(summary.get("bundle"), run_folder)

    query_files: list[Path] = []
    gold_files: list[Path] = []

    if queries_path and queries_path.exists():
        query_files.append(queries_path)
    else:
        for key in ("queries", "queries_path", "challenge_yaml", "challenges"):
            p = _resolve_candidate_path(summary.get(key), run_folder)
            if p:
                query_files.append(p)
        for cand in sorted(CHALLENGE_DIR.glob("*.yaml")):
            if "gold" not in cand.stem.lower():
                query_files.append(cand)

    if gold_path and gold_path.exists():
        gold_files.append(gold_path)
    else:
        for key in ("gold", "gold_path"):
            p = _resolve_candidate_path(summary.get(key), run_folder)
            if p:
                gold_files.append(p)
        for cand in (
            run_folder / "gold.yaml",
            run_folder / "challenge_gold.yaml",
            bundle_dir / "challenge_gold.yaml" if bundle_dir else None,
            bundle_dir / "gold.yaml" if bundle_dir else None,
        ):
            if cand and cand.exists() and cand not in gold_files:
                gold_files.append(cand)
        for cand in sorted(CHALLENGE_DIR.glob("*gold*.yaml")):
            if cand not in gold_files:
                gold_files.append(cand)

    turn_meta: dict[tuple[str, int], dict[str, Any]] = {}
    conv_turns_by_qid: dict[str, list[dict[str, Any]]] = {}

    for qf in query_files:
        data = yaml.safe_load(qf.read_text(encoding="utf-8")) or {}
        convs = data.get("conversations") or data.get("queries") or data.get("challenges") or []
        if isinstance(convs, dict):
            convs = [{"id": k, **(v if isinstance(v, dict) else {"turns": v})} for k, v in convs.items()]
        for c in convs:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            qid = str(c["id"])
            turns = list(c.get("turns") or [])
            conv_turns_by_qid[qid] = turns
            for ti, t in enumerate(turns):
                entry = turn_meta.setdefault((qid, ti), {})
                if isinstance(t, dict):
                    _merge_turn_meta(entry, t)

    for gf in gold_files:
        data = yaml.safe_load(gf.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            continue
        if "conversations" in data and isinstance(data["conversations"], list):
            for c in data["conversations"]:
                if isinstance(c, dict) and c.get("id"):
                    for ti, t in enumerate(c.get("turns") or []):
                        if isinstance(t, dict):
                            idx = int(t.get("turn_index", ti))
                            _merge_turn_meta(turn_meta.setdefault((str(c["id"]), idx), {}), t)
            continue

        for qid, g_entry in data.items():
            if qid in ("version", "evaluation_clock", "status", "bundle"):
                continue
            g_turns = g_entry.get("turns", []) if isinstance(g_entry, dict) else g_entry
            if not isinstance(g_turns, list):
                continue
            spec_turns = conv_turns_by_qid.get(str(qid), [])
            scored_indices = [
                i for i, st in enumerate(spec_turns) if isinstance(st, dict) and st.get("scored", True)
            ]
            for gi, gt in enumerate(g_turns):
                if not isinstance(gt, dict):
                    continue
                if "turn_index" in gt:
                    ti = int(gt["turn_index"])
                elif spec_turns and len(g_turns) == len(scored_indices) and len(scored_indices) != len(spec_turns):
                    ti = scored_indices[gi]
                else:
                    ti = gi
                _merge_turn_meta(turn_meta.setdefault((str(qid), ti), {}), gt)

    return turn_meta, bundle_dir


def resolve_turn_gold(row: dict[str, Any], meta: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    """Combine external gold metadata with any inline turn fields in `log.jsonl`."""
    qid = str(row.get("query_id") or "")
    ti = int(row.get("turn_index", 0))
    out: dict[str, Any] = dict(meta.get((qid, ti), {}))
    scores = row.get("scores") or {}

    if not out.get("allowed_types"):
        inline_allowed = scores.get("allowed") or scores.get("allowed_types") or row.get("allowed")
        if inline_allowed:
            out["allowed_types"] = [x.upper() for x in _as_list(inline_allowed)]
        elif row.get("expected"):
            out["allowed_types"] = [str(row["expected"]).upper()]

    if not out.get("required_values"):
        inline_vals = scores.get("required_values") or row.get("required_values") or row.get("gold_values")
        if isinstance(inline_vals, dict):
            out["required_values"] = dict(inline_vals)

    if not out.get("rubric"):
        inline_rubric = scores.get("rubric") or row.get("rubric")
        if inline_rubric:
            out["rubric"] = inline_rubric

    if not out.get("expected_tools"):
        inline_tools = scores.get("expected_tools") or row.get("expected_tools")
        if inline_tools:
            out["expected_tools"] = _as_list(inline_tools)

    return out


def is_rubric_turn(row: dict[str, Any], gold_info: dict[str, Any]) -> bool:
    scores = row.get("scores") or {}
    if scores.get("setup_turn"):
        return False
    if gold_info.get("scored") is False:
        return False
    if gold_info.get("rubric"):
        return True
    return bool(scores.get("has_rubric") or scores.get("needs_rubric") or scores.get("rubric_turn"))


def is_deterministic_pass(row: dict[str, Any]) -> bool | None:
    """Return True/False for scored turns, or None for unscored setup turns."""
    scores = row.get("scores") or {}
    if scores.get("setup_turn"):
        return None
    if row.get("success") is not None:
        return bool(row["success"])
    if "success" in scores and scores["success"] is not None:
        return bool(scores["success"])
    if "det_pass" in scores and scores["det_pass"] is not None:
        return bool(scores["det_pass"])
    return bool(scores.get("parsed", True) and scores.get("answerability_ok", True))


def format_reply_text(raw_response: str) -> str:
    """Extract clean readable reply text from raw JSON response, masking 6+ digit numbers."""
    raw = (raw_response or "").strip()
    if not raw:
        return "(empty response)"
    candidate = raw
    m = _FENCE.fullmatch(raw)
    if m:
        candidate = m.group(1)
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return mask_numbers(raw)
    if not isinstance(obj, dict):
        return mask_numbers(raw)

    lines: list[str] = []
    ans_type = obj.get("answerability")
    if ans_type:
        lines.append(f"[{ans_type}]")
    if obj.get("answer"):
        lines.append(mask_numbers(str(obj["answer"])))
    if obj.get("clarifying_question"):
        lines.append(f"Clarifying question: {mask_numbers(str(obj['clarifying_question']))}")
    calc = obj.get("calculation")
    if isinstance(calc, dict):
        steps = "; ".join(mask_numbers(str(s)) for s in (calc.get("steps") or []))
        res = calc.get("result")
        res_txt = f"{res.get('amount')} {res.get('currency')}" if isinstance(res, dict) else str(res or "")
        lines.append(f"Calculation: {steps} -> {res_txt}".strip())
    risks = obj.get("risk_indicators")
    if isinstance(risks, list) and risks:
        lines.append("Risk indicators: " + "; ".join(mask_numbers(str(r)) for r in risks))
    if obj.get("next_step"):
        lines.append(f"Next step: {mask_numbers(str(obj['next_step']))}")
    cites = obj.get("evidence")
    if isinstance(cites, list) and cites:
        cite_ids = [str(c.get("evidence_id") or "") for c in cites if isinstance(c, dict) and c.get("evidence_id")]
        if cite_ids:
            lines.append("Evidence: " + ", ".join(cite_ids))
    return "\n".join(lines) if lines else mask_numbers(raw)


def _format_det_checks(row: dict[str, Any]) -> str:
    scores = row.get("scores") or {}
    if scores.get("setup_turn"):
        return "Setup turn (not deterministically scored)"
    parts: list[str] = []
    if "parsed" in scores:
        parts.append(f"parsed={'OK' if scores['parsed'] else 'FAIL'}")
    elif "parsed_ok" in row:
        parts.append(f"parsed={'OK' if row['parsed_ok'] else 'FAIL'}")
    if "answerability_ok" in scores:
        parts.append(f"type={'OK' if scores['answerability_ok'] else 'FAIL'}")

    vals = scores.get("values")
    if isinstance(vals, dict) and vals:
        v_str = ", ".join(f"{k}={'OK' if ok else 'FAIL'}" for k, ok in vals.items())
        parts.append(f"values=[{v_str}]")

    checks = scores.get("checks") or scores.get("check_results")
    if isinstance(checks, dict) and checks:
        c_str = ", ".join(f"{k}={'OK' if ok else 'FAIL'}" for k, ok in checks.items())
        parts.append(f"checks=[{c_str}]")

    if scores.get("evidence_recall") is not None:
        parts.append(f"ev_recall={scores['evidence_recall']:.2f}")
    if scores.get("must_not_hits"):
        parts.append(f"must_not_hits={scores['must_not_hits']}")
    if row.get("notes"):
        parts.append(f"notes={mask_numbers(str(row['notes']))}")
    return " | ".join(parts) if parts else ("PASS" if is_deterministic_pass(row) else "FAIL")


def _format_rubric(rubric: Any) -> str:
    if isinstance(rubric, list):
        return "\n".join(f"- {x}" for x in rubric)
    if isinstance(rubric, dict):
        return "\n".join(f"{k}: {v}" for k, v in rubric.items())
    return str(rubric)


def _format_required_values(req: dict[str, Any]) -> str:
    if not req:
        return "None"
    return ", ".join(f"{k}: {mask_sensitive_value(str(k), v)}" for k, v in req.items())


def build_review_html(
    run_folder: Path,
    rows: list[dict[str, Any]],
    meta: dict[tuple[str, int], dict[str, Any]],
) -> str:
    """Render self-contained HTML string with 0/1/2 rubric controls and CSV export."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        qid = str(row.get("query_id") or "")
        grouped.setdefault(qid, []).append(row)

    total_turns = 0
    rubric_turns = 0
    sections: list[str] = []

    for qid, qrows in grouped.items():
        qrows_sorted = sorted(qrows, key=lambda r: (int(r.get("turn_index", 0)), str(r.get("configuration") or "")))
        cards: list[str] = []
        for row in qrows_sorted:
            total_turns += 1
            ti = int(row.get("turn_index", 0))
            cfg = str(row.get("configuration") or "")
            gold_info = resolve_turn_gold(row, meta)
            det_pass = is_deterministic_pass(row)
            rubric_flag = is_rubric_turn(row, gold_info)
            if rubric_flag:
                rubric_turns += 1

            if det_pass is None:
                badge_cls, badge_lbl = "setup", "SETUP"
            elif det_pass:
                badge_cls, badge_lbl = "pass", "DET PASS"
            else:
                badge_cls, badge_lbl = "fail", "DET FAIL"

            allowed_str = ", ".join(gold_info.get("allowed_types") or []) or "—"
            req_str = _format_required_values(gold_info.get("required_values") or {})
            rubric_val = gold_info.get("rubric")
            rubric_html = (
                f"<pre class='box rubric-box'>{html.escape(_format_rubric(rubric_val))}</pre>"
                if rubric_val
                else "<span class='muted'>None (deterministic-only turn)</span>"
            )

            tool_lines = format_tool_calls(extract_tool_calls(row))
            tools_html = (
                "<ul>" + "".join(f"<li><code>{html.escape(line)}</code></li>" for line in tool_lines) + "</ul>"
                if tool_lines
                else "<span class='muted'>None</span>"
            )

            rubric_controls = ""
            if rubric_flag:
                rubric_controls = (
                    '<div class="rubric-controls rubric-row" '
                    f'data-query-id="{html.escape(qid)}" '
                    f'data-turn-index="{ti}" '
                    f'data-configuration="{html.escape(cfg)}">'
                    '<label>Rubric score (0/1/2): '
                    '<select class="rubric-score">'
                    '<option value="">-- unscored --</option>'
                    '<option value="0">0 - Fail</option>'
                    '<option value="1">1 - Partial</option>'
                    '<option value="2">2 - Pass</option>'
                    '</select></label>'
                    '<label class="notes-wrap">Notes: '
                    '<textarea class="rubric-notes" rows="2" '
                    'placeholder="Notes (start with TEST: if test issue)"></textarea>'
                    '</label>'
                    '</div>'
                )

            cards.append(
                "<article class='turn-card' "
                f"data-det-status='{badge_cls}' data-has-rubric='{'1' if rubric_flag else '0'}'>"
                "<div class='turn-head'>"
                f"<span><strong>{html.escape(qid)}</strong> · Turn {ti} · <code>{html.escape(cfg)}</code></span>"
                f"<span class='badge {badge_cls}'>{badge_lbl}</span>"
                "</div>"
                f"<div class='field'><strong>Turn text:</strong> {html.escape(mask_numbers(str(row.get('turn_text') or '')))}</div>"
                f"<div class='grid2'>"
                f"<div class='field'><strong>Allowed types:</strong> {html.escape(allowed_str)}</div>"
                f"<div class='field'><strong>Required values:</strong> {html.escape(req_str)}</div>"
                f"</div>"
                f"<div class='field'><strong>Rubric:</strong> {rubric_html}</div>"
                f"<div class='field'><strong>Reply text:</strong><pre class='box'>{html.escape(format_reply_text(str(row.get('raw_response') or '')))}</pre></div>"
                f"<div class='field'><strong>Deterministic checks:</strong> <code>{html.escape(_format_det_checks(row))}</code></div>"
                f"<div class='field'><strong>Tool calls:</strong> {tools_html}</div>"
                f"{rubric_controls}"
                "</article>"
            )
        sections.append(f"<section class='conv-block'><h2>{html.escape(qid)}</h2>\n" + "\n".join(cards) + "\n</section>")

    storage_key = f"cashbooks_challenge_review_{run_folder.name}"
    body = "\n".join(sections) if sections else "<p>No turns logged.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Challenge Review Sheet — {html.escape(run_folder.name)}</title>
<style>
  :root {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1f2937; }}
  body {{ max-width: 1120px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
  .topbar {{ position: sticky; top: 0; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px;
             padding: 12px 16px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
             justify-content: space-between; z-index: 10; margin-bottom: 18px; box-shadow: 0 2px 6px rgba(0,0,0,.05); }}
  .topbar h1 {{ margin: 0; font-size: 1.15rem; }}
  .controls {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  button {{ background: #1d4ed8; color: #fff; border: none; border-radius: 6px; padding: 8px 14px;
            font-weight: 600; cursor: pointer; }}
  button:hover {{ background: #1e40af; }}
  .conv-block {{ margin-bottom: 24px; }}
  .conv-block h2 {{ margin: 0 0 10px; padding-bottom: 4px; border-bottom: 2px solid #cbd5e1; font-size: 1.05rem; }}
  .turn-card {{ background: #fff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }}
  .turn-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .badge {{ padding: 2px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }}
  .badge.pass {{ background: #dcfce7; color: #166534; }}
  .badge.fail {{ background: #fee2e2; color: #991b1b; }}
  .badge.setup {{ background: #e2e8f0; color: #334155; }}
  .grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; }}
  .field {{ margin: 6px 0; font-size: 0.92rem; }}
  .muted {{ color: #64748b; font-style: italic; }}
  pre.box {{ background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px;
             white-space: pre-wrap; margin: 4px 0 0; font-size: 0.86rem; font-family: ui-monospace, monospace; }}
  pre.rubric-box {{ background: #fefce8; border-color: #fde68a; }}
  ul {{ margin: 4px 0 0; padding-left: 20px; }}
  .rubric-controls {{ margin-top: 10px; padding-top: 10px; border-top: 1px dashed #cbd5e1;
                      display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-start; background: #f8fafc; padding: 10px; border-radius: 6px; }}
  .notes-wrap {{ flex: 1; min-width: 260px; display: flex; flex-direction: column; gap: 4px; }}
  textarea.rubric-notes {{ width: 100%; box-sizing: border-box; font-family: inherit; padding: 6px; border: 1px solid #94a3b8; border-radius: 4px; }}
  select.rubric-score {{ padding: 5px 8px; border: 1px solid #94a3b8; border-radius: 4px; font-size: 0.9rem; }}
  @media print {{ .topbar {{ position: static; }} button {{ display: none; }} }}
</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1>Challenge Run Review: {html.escape(run_folder.name)}</h1>
    <div style="font-size:0.85rem;color:#475569;">Turns: {total_turns} · Rubric turns: {rubric_turns} · <span id="scored-count">Scored: 0/{rubric_turns}</span></div>
  </div>
  <div class="controls">
    <label style="font-size:0.86rem;">Filter:
      <select id="view-filter">
        <option value="all">All turns</option>
        <option value="fail">Det fails only</option>
        <option value="rubric">Rubric turns only</option>
      </select>
    </label>
    <button type="button" id="export-csv-btn">Export CSV</button>
  </div>
</div>
{body}
<script>
(function() {{
  const STORAGE_KEY = {json.dumps(storage_key)};
  const rows = Array.from(document.querySelectorAll('.rubric-row'));
  const countEl = document.getElementById('scored-count');

  function rowKey(el) {{
    return [el.dataset.queryId, el.dataset.turnIndex, el.dataset.configuration].join('|');
  }}

  function csvEscape(val) {{
    const s = String(val == null ? '' : val);
    return /[",\\r\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }}

  function saveState() {{
    const data = {{}};
    let scored = 0;
    for (const el of rows) {{
      const score = el.querySelector('.rubric-score').value;
      const notes = el.querySelector('.rubric-notes').value;
      if (score !== '') scored += 1;
      data[rowKey(el)] = {{ score, notes }};
    }}
    if (countEl) countEl.textContent = 'Scored: ' + scored + '/' + rows.length;
    try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }} catch (e) {{}}
  }}

  try {{
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
    for (const el of rows) {{
      const item = saved[rowKey(el)];
      if (item) {{
        if (item.score !== undefined) el.querySelector('.rubric-score').value = item.score;
        if (item.notes !== undefined) el.querySelector('.rubric-notes').value = item.notes;
      }}
    }}
  }} catch (e) {{}}

  for (const el of rows) {{
    el.querySelector('.rubric-score').addEventListener('change', saveState);
    el.querySelector('.rubric-notes').addEventListener('input', saveState);
  }}
  saveState();

  const filterEl = document.getElementById('view-filter');
  if (filterEl) {{
    filterEl.addEventListener('change', function() {{
      const mode = filterEl.value;
      for (const card of document.querySelectorAll('.turn-card')) {{
        const show = mode === 'all' ||
          (mode === 'fail' && card.dataset.detStatus === 'fail') ||
          (mode === 'rubric' && card.dataset.hasRubric === '1');
        card.style.display = show ? '' : 'none';
      }}
    }});
  }}

  document.getElementById('export-csv-btn').addEventListener('click', function() {{
    const lines = ['query_id,turn_index,configuration,rubric_score,notes'];
    for (const el of rows) {{
      const vals = [
        el.dataset.queryId,
        el.dataset.turnIndex,
        el.dataset.configuration,
        el.querySelector('.rubric-score').value,
        el.querySelector('.rubric-notes').value
      ];
      lines.push(vals.map(csvEscape).join(','));
    }}
    const blob = new Blob([lines.join('\\n') + '\\n'], {{ type: 'text/csv;charset=utf-8;' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'human_scores.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }});
}})();
</script>
</body>
</html>
"""


def generate_review_sheet(
    run_folder: Path,
    gold_path: Path | None = None,
    queries_path: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """Build <run_folder>/review.html from log.jsonl and challenge gold/queries metadata."""
    rows = load_log_rows(run_folder)
    meta, _ = load_challenge_metadata(run_folder, gold_path=gold_path, queries_path=queries_path)
    out = out_path or (run_folder / "review.html")
    out.write_text(build_review_html(run_folder, rows, meta), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a self-contained HTML review sheet for a challenge run.")
    ap.add_argument("run_folder", type=Path, help="Run directory containing log.jsonl")
    ap.add_argument("--gold", type=Path, help="Optional gold YAML override")
    ap.add_argument("--queries", type=Path, help="Optional challenge queries YAML override")
    ap.add_argument("--out", type=Path, help="Output HTML path (default <run_folder>/review.html)")
    a = ap.parse_args()

    out = generate_review_sheet(a.run_folder, gold_path=a.gold, queries_path=a.queries, out_path=a.out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
