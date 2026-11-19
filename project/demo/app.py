"""Local Streamlit web chat for CashBooks Assist.

    streamlit run project/demo/app.py
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from cashbooks.attention import find_attention_items
from cashbooks.contracts.common import Answerability
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.demo import ChatSession, ChatTurnResult
from cashbooks.llm.base import LLM
from cashbooks.llm.claude import ClaudeLLM
from cashbooks.llm.scripted import ScriptedLLM

PROJECT = Path(__file__).resolve().parents[1]
BUNDLE = PROJECT / "data" / "dev" / "cafe_01"
DEFAULT_CONFIG = "C3"
SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
_SAFE_TESTER = re.compile(r"[^A-Za-z0-9_-]+")

CONFIGS = ["C0", "C1", "C2", "C3", "C4"]
CONFIG_HELP = {
    "C0": "Full raw corpus in prompt",
    "C1": "BM25 over raw document chunks",
    "C2": "BM25 over extracted records",
    "C3": "Read-only tools over extracted records",
    "C4": "Read-only tools over gold records",
}

EXAMPLE_QUESTIONS = [
    ("Q01 · Due in 7 days", "What bills are due in the next seven days?"),
    ("Q04 · NS-1048 paid?", "Did I already pay invoice NS-1048?"),
    ("Q06 · GP-228 balance", "What remains unpaid on GP-228 after the partial payment?"),
    ("Q12 · BW-771 bank change", "Did the payment details on BW-771 change?"),
    ("Q20 · Pay it now", "Pay it now."),
    ("Q29 · Coffee stock", "How many coffee bags do I have in stock right now?"),
]

BADGE_COLORS = {
    Answerability.ANSWER: ("#1b7f4b", "#e7f5ed"),
    Answerability.CLARIFY: ("#1d5fa7", "#e8f1fb"),
    Answerability.ABSTAIN: ("#4b5563", "#f1f3f5"),
    Answerability.WARN: ("#b45309", "#fef3c7"),
}


def _render_badge(ans: Answerability | None, parse_error: str | None) -> None:
    if ans is None:
        st.markdown(
            '<span style="background:#fee2e2;color:#991b1b;padding:2px 10px;border-radius:12px;'
            'font-weight:600;font-size:0.85em;">PARSE ERROR</span>',
            unsafe_allow_html=True,
        )
        if parse_error:
            st.error(parse_error)
        return
    fg, bg = BADGE_COLORS[ans]
    st.markdown(
        f'<span style="background:{bg};color:{fg};padding:2px 10px;border-radius:12px;'
        f'font-weight:600;font-size:0.85em;">{ans.value}</span>',
        unsafe_allow_html=True,
    )


def _render_reply(res: ChatTurnResult) -> None:
    _render_badge(res.answerability, res.parse_error)
    if res.answer:
        st.markdown(res.answer)
    if res.clarifying_question:
        st.info(res.clarifying_question)
    if res.calculation_steps or res.calculation_result:
        steps = "  \n".join(res.calculation_steps)
        tail = f"  \n**Result:** {res.calculation_result}" if res.calculation_result else ""
        st.markdown(f"**Calculation**  \n{steps}{tail}")
    if res.risk_indicators:
        for r in res.risk_indicators:
            st.warning(r)
    if res.next_step:
        st.caption(f"Next step: {res.next_step}")

    with st.expander("Evidence", expanded=True):
        if not res.citations:
            st.write("No citations.")
        else:
            for c in res.citations:
                st.markdown(f"**`{c.evidence_id}`** — {c.supports}")
                st.code(c.quote, language=None)

    with st.expander("How it answered"):
        st.caption(
            f"Config `{res.config_name}` · {res.latency_ms} ms · "
            f"{res.input_tokens} in / {res.output_tokens} out tokens"
        )
        if res.tool_calls:
            for tc in res.tool_calls:
                st.markdown(f"**Tool `{tc.name}`** `{mask_numbers(str(tc.args))}`")
                st.code(tc.result_preview, language=None)
        elif res.retrieved_chunks:
            for ch in res.retrieved_chunks:
                st.markdown(f"- `{ch['chunk_id']}` ({ch.get('source', '')})")
        else:
            st.write("No tool calls or retrieved chunks recorded.")


def _safe_tester_slug(tester: str) -> str:
    slug = _SAFE_TESTER.sub("-", tester.strip().lower()).strip("-")
    return slug or "anonymous"


def log_demo_turn(
    tester: str,
    question: str,
    res: ChatTurnResult,
    sessions_dir: Path = SESSIONS_DIR,
    now: datetime | None = None,
    bundle: str = BUNDLE.name,
    thumbs: str | None = None,
    comment: str = "",
) -> Path:
    """Append one masked demo turn record to sessions/<date>-<tester>.jsonl."""
    ts = now or datetime.now(timezone.utc)
    slug = _safe_tester_slug(tester)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{ts.date().isoformat()}-{slug}.jsonl"
    norm_thumbs = thumbs if thumbs in ("up", "down") else None
    masked_reply = mask_numbers(res.answer)
    masked_comment = mask_numbers(comment.strip()) if comment else ""
    record = {
        "tester": tester.strip() or "anonymous",
        "timestamp": ts.isoformat(),
        "bundle": bundle,
        "config": res.config_name,
        "configuration": res.config_name,
        "question": mask_numbers(question),
        "reply": masked_reply,
        "masked_answer": masked_reply,
        "answerability": res.answerability.value if res.answerability else None,
        "cited_ids": [c.evidence_id for c in res.citations],
        "latency_ms": res.latency_ms,
        "thumbs": norm_thumbs,
        "comment": masked_comment,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return path


def update_turn_feedback(
    log_path: Path,
    line_index: int = -1,
    thumbs: str | None = None,
    comment: str | None = None,
) -> dict:
    """Update thumbs ('up'/'down'/None) and/or optional comment on a logged turn in log_path."""
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"empty session log: {log_path}")
    idx = line_index if line_index >= 0 else len(lines) + line_index
    if idx < 0 or idx >= len(lines):
        raise IndexError(f"turn index {line_index} out of range for {len(lines)} lines")
    record = json.loads(lines[idx])
    if thumbs is not None:
        record["thumbs"] = thumbs if thumbs in ("up", "down") else None
    if comment is not None:
        record["comment"] = mask_numbers(comment.strip())
    lines[idx] = json.dumps(record)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return record


def _make_demo_llm() -> LLM:
    if os.environ.get("CASHBOOKS_DEMO_LLM", "").strip().lower() == "scripted":
        return ScriptedLLM(
            replies={
                "seven days": {
                    "answerability": "ANSWER",
                    "answer": "One open bill is due in the next seven days: NS-1062 ($1,073.25 USD after credit CN-0457), due 2026-10-01.",
                    "as_of": "2026-09-24",
                    "evidence": [
                        {"evidence_id": "span_inv_NS-1062_stated_due_date", "supports": "due 2026-10-01"},
                        {"evidence_id": "span_cn_CN-0457_total", "supports": "45.00 USD credit"},
                    ],
                },
                "NS-1048": {
                    "answerability": "ANSWER",
                    "answer": "Yes. Invoice NS-1048 ($842.00 USD) was paid in full on 2026-09-12.",
                    "as_of": "2026-09-24",
                    "evidence": [
                        {"evidence_id": "span_inv_NS-1048_total", "supports": "842.00 USD total"},
                        {"evidence_id": "txn_0193", "supports": "842.00 USD bank debit"},
                    ],
                },
                "GP-228": {
                    "answerability": "WARN",
                    "answer": "Invoice GP-228 totals $512.30 USD. Only a candidate $300.00 USD bank debit (2026-09-09) appears, leaving $212.30 USD if applied, which conflicts with the vendor message claiming payment in full.",
                    "as_of": "2026-09-24",
                    "evidence": [
                        {"evidence_id": "span_inv_GP-228_total", "supports": "512.30 USD total"},
                        {"evidence_id": "txn_0181", "supports": "300.00 USD ACH debit"},
                        {"evidence_id": "span_msg_m03", "supports": "vendor claims paid in full"},
                    ],
                    "risk_indicators": ["Vendor message claims GP-228 is paid in full, but bank records show only a 300.00 USD debit."],
                    "next_step": "Confirm the applied payments with Miguel Ortega at (510) 555-0187.",
                },
                "BW-771": {
                    "answerability": "WARN",
                    "answer": "Yes. BW-771 lists Summit Digital Bank account ****5507, which differs from the verified Golden Gate Credit Union account ****4417 on file for BeanWorks Coffee Roasters.",
                    "as_of": "2026-09-24",
                    "evidence": [
                        {"evidence_id": "span_inv_BW-771_remit_account", "supports": "printed account ****5507"},
                        {"evidence_id": "vh_v_beanworks", "supports": "verified account ****4417"},
                    ],
                    "risk_indicators": ["Printed remittance account ****5507 differs from verified vendor record ****4417."],
                    "next_step": "Call Priya Shah at (415) 555-0119 to confirm before paying.",
                },
                "Pay it now": {
                    "answerability": "ABSTAIN",
                    "answer": "I am a read-only bookkeeping assistant and cannot initiate payments or modify records.",
                    "as_of": "2026-09-24",
                    "evidence": [],
                },
                "coffee bags": {
                    "answerability": "ABSTAIN",
                    "answer": "I only have access to bills, credit notes, bank rows, and vendor messages, not live inventory counts.",
                    "as_of": "2026-09-24",
                    "evidence": [],
                },
            },
            tool_plan={
                "seven days": [("list_open_bills", {"as_of": "2026-09-24"})],
                "NS-1048": [("get_bill_status", {"invoice_number": "NS-1048", "as_of": "2026-09-24"})],
                "GP-228": [("get_bill_status", {"invoice_number": "GP-228", "as_of": "2026-09-24"})],
                "BW-771": [("compare_vendor_payment_details", {"invoice_number": "BW-771"})],
            },
        )
    return ClaudeLLM()


def _get_session(config_name: str = DEFAULT_CONFIG) -> ChatSession:
    if "chat_session" not in st.session_state:
        llm = _make_demo_llm()
        st.session_state.chat_session = ChatSession(BUNDLE, config_name, llm)
        st.session_state.messages = []
    return st.session_state.chat_session


def _render_feedback_controls(msg: dict, msg_idx: int) -> None:
    log_path_str = msg.get("log_path")
    log_line = msg.get("log_line")
    if not log_path_str or log_line is None:
        return
    log_path = Path(log_path_str)
    current_thumbs = msg.get("thumbs")
    current_comment = msg.get("comment", "")

    col_up, col_down, col_comment = st.columns([1, 1, 5])
    with col_up:
        up_label = "👍 Helpful ✓" if current_thumbs == "up" else "👍 Helpful"
        if st.button(up_label, key=f"thumbs_up_{msg_idx}", use_container_width=True):
            msg["thumbs"] = "up"
            update_turn_feedback(log_path, log_line, thumbs="up", comment=msg.get("comment", ""))
            st.rerun()
    with col_down:
        down_label = "👎 Issue ✓" if current_thumbs == "down" else "👎 Issue"
        if st.button(down_label, key=f"thumbs_down_{msg_idx}", use_container_width=True):
            msg["thumbs"] = "down"
            update_turn_feedback(log_path, log_line, thumbs="down", comment=msg.get("comment", ""))
            st.rerun()
    with col_comment:
        new_comment = st.text_input(
            "Optional feedback comment",
            value=current_comment,
            placeholder="Optional comment on this reply...",
            key=f"feedback_comment_{msg_idx}",
            label_visibility="collapsed",
        )
        if new_comment != current_comment:
            msg["comment"] = new_comment
            update_turn_feedback(log_path, log_line, thumbs=msg.get("thumbs"), comment=new_comment)


def main() -> None:
    st.set_page_config(page_title="CashBooks Assist", page_icon="☕", layout="centered")
    st.title("CashBooks Assist")

    with st.sidebar:
        st.header("Settings")
        tester_name = st.text_input("Tester name", value="", placeholder="e.g. alex")
        picked = st.selectbox(
            "Configuration",
            CONFIGS,
            index=CONFIGS.index(DEFAULT_CONFIG),
            format_func=lambda c: f"{c} — {CONFIG_HELP[c]}",
        )
        session = _get_session(picked)
        if picked != session.config_name:
            session.switch_config(picked)
            st.session_state.messages = []

        if st.button("New conversation", use_container_width=True):
            session.reset()
            st.session_state.messages = []
            st.session_state.show_attention = False
            st.rerun()

        if st.button("What needs my attention?", use_container_width=True):
            st.session_state.show_attention = not st.session_state.get("show_attention", False)

        st.info(
            f"Business: **{session.business_name}** (`{BUNDLE.name}`)  \n"
            f"Evaluation clock: **{session.as_of.isoformat()}**  \n"
            f"Configuration: **{session.config_name}** ({CONFIG_HELP[session.config_name]})"
        )
        st.subheader("Example questions")
        queued_prompt: str | None = None
        for label, qtext in EXAMPLE_QUESTIONS:
            if st.button(label, use_container_width=True):
                queued_prompt = qtext

    st.caption(
        f"Business: **{session.business_name}** (`{BUNDLE.name}`, as of `{session.as_of.isoformat()}`) · "
        f"Configuration: **{session.config_name}** — {CONFIG_HELP[session.config_name]}"
    )

    if st.session_state.get("show_attention"):
        att_store = (
            session.extracted_store
            if session.config_name in ("C2", "C3") and session.extracted_store is not None
            else session.gold_store
        )
        att_items = find_attention_items(att_store, session.as_of)
        with st.expander(f"What needs my attention ({len(att_items)} items)", expanded=True):
            if not att_items:
                st.write("No attention items found.")
            else:
                for it in att_items:
                    ev = ", ".join(f"`{e}`" for e in it.evidence_ids) if it.evidence_ids else "—"
                    st.markdown(f"- **`{it.kind}`** — {it.description} (evidence: {ev})")

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                _render_reply(msg["result"])
                _render_feedback_controls(msg, idx)

    prompt = st.chat_input("Ask about Ember & Oat Cafe's bills or payments...") or queued_prompt
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                res = session.ask(prompt)
            _render_reply(res)
            log_path = log_demo_turn(tester_name, prompt, res, bundle=BUNDLE.name)
            line_count = len([ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()])
            asst_msg = {
                "role": "assistant",
                "result": res,
                "log_path": str(log_path),
                "log_line": line_count - 1,
                "thumbs": None,
                "comment": "",
            }
            st.session_state.messages.append(asst_msg)
            _render_feedback_controls(asst_msg, len(st.session_state.messages) - 1)


if __name__ == "__main__":
    main()
