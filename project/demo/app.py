"""Local Streamlit web chat for CashBooks Assist.

    streamlit run project/demo/app.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.postprocess import mask_numbers
from cashbooks.demo import ChatSession, ChatTurnResult
from cashbooks.llm.claude import ClaudeLLM

PROJECT = Path(__file__).resolve().parents[1]
BUNDLE = PROJECT / "data" / "dev" / "cafe_01"
SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
_SAFE_TESTER = re.compile(r"[^A-Za-z0-9_-]+")

CONFIGS = ["C1", "C2", "C3", "C4"]
CONFIG_HELP = {
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

    with st.expander("Evidence"):
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
                st.markdown(f"**Tool `{tc.name}`** `{tc.args}`")
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
) -> Path:
    """Append one masked demo turn record to sessions/<date>-<tester>.jsonl."""
    ts = now or datetime.now(timezone.utc)
    slug = _safe_tester_slug(tester)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{ts.date().isoformat()}-{slug}.jsonl"
    record = {
        "tester": tester.strip() or "anonymous",
        "timestamp": ts.isoformat(),
        "config": res.config_name,
        "question": mask_numbers(question),
        "answerability": res.answerability.value if res.answerability else None,
        "masked_answer": mask_numbers(res.answer),
        "cited_ids": [c.evidence_id for c in res.citations],
        "latency_ms": res.latency_ms,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return path


def _get_session(config_name: str) -> ChatSession:
    if "chat_session" not in st.session_state:
        llm = ClaudeLLM()
        st.session_state.chat_session = ChatSession(BUNDLE, config_name, llm)
        st.session_state.messages = []
    return st.session_state.chat_session


def main() -> None:
    st.set_page_config(page_title="CashBooks Assist", page_icon="☕", layout="centered")
    st.title("CashBooks Assist")

    with st.sidebar:
        st.header("Settings")
        tester_name = st.text_input("Tester name", value="", placeholder="e.g. alex")
        picked = st.selectbox(
            "Configuration",
            CONFIGS,
            index=CONFIGS.index("C3"),
            format_func=lambda c: f"{c} — {CONFIG_HELP[c]}",
        )
        session = _get_session(picked)
        if picked != session.config_name:
            session.switch_config(picked)
            st.session_state.messages = []

        if st.button("New conversation", use_container_width=True):
            session.reset()
            st.session_state.messages = []
            st.rerun()

        st.info("Data: synthetic café (**Ember & Oat Cafe**) as of **2026-09-24**.")
        st.subheader("Example questions")
        queued_prompt: str | None = None
        for label, qtext in EXAMPLE_QUESTIONS:
            if st.button(label, use_container_width=True):
                queued_prompt = qtext

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                _render_reply(msg["result"])

    prompt = st.chat_input("Ask about Ember & Oat Cafe's bills or payments...") or queued_prompt
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                res = session.ask(prompt)
            _render_reply(res)
        log_demo_turn(tester_name, prompt, res)
        st.session_state.messages.append({"role": "assistant", "result": res})


if __name__ == "__main__":
    main()
