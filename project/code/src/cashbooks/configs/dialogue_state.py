"""Explicit structured dialogue state derived strictly from displayed turns.

Never inspects gold files, hidden tool outputs, or database tables: all state comes
only from user turns and the assistant's displayed replies so C0-C4 share identical
follow-up tracking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INVOICE_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z]{2,6}-\d{2,6})(?![A-Za-z0-9_])")
_DATE_ISO_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MONTH_YEAR_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
    re.I,
)
_REL_DATE_RE = re.compile(r"\b(today|this week|this month|last month)\b", re.I)
_CURRENCY_RE = re.compile(r"\b(USD|CAD|EUR|GBP|AUD)\b")
_STATUS_RE = re.compile(r"\b(overdue|unpaid|open|partly paid|partially paid|settled|paid)\b", re.I)

_ORDINALS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(?:the\s+)?(?:first|1st)(?:\s+one)?\b|#1\b|\bitem\s*1\b", re.I), 0),
    (re.compile(r"\b(?:the\s+)?(?:second|2nd)(?:\s+one)?\b|#2\b|\bitem\s*2\b", re.I), 1),
    (re.compile(r"\b(?:the\s+)?(?:third|3rd)(?:\s+one)?\b|#3\b|\bitem\s*3\b", re.I), 2),
    (re.compile(r"\b(?:the\s+)?(?:fourth|4th)(?:\s+one)?\b|#4\b|\bitem\s*4\b", re.I), 3),
    (re.compile(r"\b(?:the\s+)?(?:fifth|5th)(?:\s+one)?\b|#5\b|\bitem\s*5\b", re.I), 4),
    (re.compile(r"\b(?:the\s+)?last(?:\s+one)?\b", re.I), -1),
]
_BEFORE_RE = re.compile(r"\b(?:the\s+)?(?:one\s+before\s+that|before\s+that|previous\s+one|prior\s+one)\b", re.I)
_NEXT_RE = re.compile(r"\b(?:the\s+)?(?:one\s+after\s+that|after\s+that|next\s+one)\b", re.I)
_PHRASE_ONE_RE = re.compile(r"\bthe\s+([A-Za-z0-9&'.-]+(?:\s+[A-Za-z0-9&'.-]+){0,3}?)\s+(?:one|bill|invoice|vendor)\b", re.I)
_SINGULAR_REF_RE = re.compile(
    r"\b(?:it|its|that\s+one|that\s+bill|that\s+invoice|this\s+one|this\s+bill|this\s+invoice)\b",
    re.I,
)
_PLURAL_REF_RE = re.compile(r"\b(?:them|those|both|those\s+bills|those\s+invoices)\b", re.I)
_FOLLOWUP_START_RE = re.compile(r"^\s*(?:what\s+about|how\s+about|and\b|same\s+for|what\s+if)\b", re.I)

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "one", "bill", "invoice", "vendor", "please", "yes", "no", "that", "this",
        "it", "for", "of", "in", "on", "to", "with", "about", "status", "pay", "check", "me", "us",
    }
)


@dataclass
class ReferenceResolution:
    """Result of resolving follow-up references in a user message against DialogueState."""

    resolved_invoice: str | None = None
    resolved_vendor: str | None = None
    ambiguous_reason: str | None = None
    matched_rule: str | None = None
    is_plural_displayed: bool = False


@dataclass
class DialogueState:
    """Structured conversation state extracted exclusively from displayed replies and user turns."""

    displayed_invoices: list[str] = field(default_factory=list)
    invoice_snippets: dict[str, str] = field(default_factory=dict)
    clarifying_options: list[str] = field(default_factory=list)
    selected_invoice: str | None = None
    selected_vendor: str | None = None
    date_filter: str | None = None
    currency_filter: str | None = None
    status_filter: str | None = None
    unresolved_clarification: str | None = None
    turn_count: int = 0

    def clone(self) -> DialogueState:
        return DialogueState(
            displayed_invoices=list(self.displayed_invoices),
            invoice_snippets=dict(self.invoice_snippets),
            clarifying_options=list(self.clarifying_options),
            selected_invoice=self.selected_invoice,
            selected_vendor=self.selected_vendor,
            date_filter=self.date_filter,
            currency_filter=self.currency_filter,
            status_filter=self.status_filter,
            unresolved_clarification=self.unresolved_clarification,
            turn_count=self.turn_count,
        )


def _body_lines_from_displayed(assistant_text: str) -> tuple[list[str], str | None]:
    """Split displayed assistant text into primary answer lines and any clarifying question."""
    body_lines: list[str] = []
    clarify_line: str | None = None
    for line in assistant_text.splitlines():
        if line.startswith("Clarifying question:"):
            clarify_line = line.split(":", 1)[1].strip()
            body_lines.append(clarify_line)
        elif line.startswith(("Calculation:", "Risk indicators:", "Next step:")):
            continue
        else:
            body_lines.append(line)
    if clarify_line is None:
        stripped = assistant_text.strip()
        if stripped.endswith("?") and "?" in stripped:
            last_q = stripped.split("\n")[-1].strip()
            if len(last_q) <= 240:
                clarify_line = last_q
    return body_lines, clarify_line


def extract_displayed_invoices(assistant_text: str) -> tuple[list[str], dict[str, str]]:
    """Extract ordered invoice IDs and their displayed line snippets from an assistant reply."""
    body_lines, _ = _body_lines_from_displayed(assistant_text)
    seen: list[str] = []
    snippets: dict[str, str] = {}
    for line in body_lines:
        for inv in _INVOICE_RE.findall(line):
            if inv not in snippets:
                seen.append(inv)
                snippets[inv] = " ".join(line.strip().split())[:180]
    return seen, snippets


def extract_clarifying_options(clarify_text: str | None) -> list[str]:
    """Parse candidate clarifying options from a clarifying question when explicitly listed."""
    if not clarify_text:
        return []
    text = clarify_text.strip().rstrip("?.")
    segment = text.split(":", 1)[1].strip() if ":" in text else ""
    if not segment:
        m = re.search(r"(?:between|mean|which(?:\s+\w+){1,2})\s+(.+)$", text, re.I)
        if m:
            segment = m.group(1).strip()
    if not segment:
        return []
    parts = [p.strip(" ()\"'") for p in re.split(r"\s*,\s*or\s+|\s+or\s+|\s*,\s*", segment) if p.strip()]
    return [p for p in parts if 1 <= len(p) <= 80][:8]


def _extract_filters(text: str) -> tuple[str | None, str | None, str | None]:
    date_f: str | None = None
    if m := _DATE_ISO_RE.search(text):
        date_f = m.group(1)
    elif m := _MONTH_YEAR_RE.search(text):
        date_f = f"{m.group(1).title()} {m.group(2)}"
    elif m := _REL_DATE_RE.search(text):
        date_f = m.group(1).lower()

    curr_f = m.group(1).upper() if (m := _CURRENCY_RE.search(text)) else None
    stat_f = m.group(1).lower() if (m := _STATUS_RE.search(text)) else None
    return date_f, curr_f, stat_f


def _has_followup_marker(user_text: str, state: DialogueState) -> bool:
    if any(pat.search(user_text) for pat, _ in _ORDINALS):
        return True
    if _BEFORE_RE.search(user_text) or _NEXT_RE.search(user_text):
        return True
    if _PHRASE_ONE_RE.search(user_text) or _SINGULAR_REF_RE.search(user_text) or _PLURAL_REF_RE.search(user_text):
        return True
    if _FOLLOWUP_START_RE.search(user_text):
        return True
    if state.unresolved_clarification and len(user_text.split()) <= 8 and "?" not in user_text:
        return True
    return False


def _match_fragment_candidates(phrase: str, items: dict[str, str]) -> list[str]:
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9&-]+", phrase) if t.lower() not in _STOPWORDS and len(t) >= 2]
    if not tokens:
        return []
    hits: list[str] = []
    for key, text in items.items():
        hay = f"{key} {text}".lower()
        if all(tok in hay for tok in tokens):
            hits.append(key)
    return hits


def resolve_reference(state: DialogueState, user_text: str) -> ReferenceResolution:
    """Resolve references in `user_text` strictly against `state`; leave uncertain ones ambiguous."""
    explicit_invs = list(dict.fromkeys(_INVOICE_RE.findall(user_text)))
    if len(explicit_invs) == 1:
        return ReferenceResolution(resolved_invoice=explicit_invs[0], matched_rule="explicit_invoice")
    if len(explicit_invs) > 1:
        return ReferenceResolution(matched_rule="explicit_multi_invoice")

    for pat, idx in _ORDINALS:
        if pat.search(user_text):
            if not state.displayed_invoices:
                return ReferenceResolution(
                    ambiguous_reason="ordinal reference used, but no ordered list has been displayed yet"
                )
            if idx != -1 and idx >= len(state.displayed_invoices):
                return ReferenceResolution(
                    ambiguous_reason=f"ordinal refers to item #{idx + 1}, but only {len(state.displayed_invoices)} item(s) were displayed"
                )
            return ReferenceResolution(
                resolved_invoice=state.displayed_invoices[idx],
                matched_rule="ordinal_from_displayed_list",
            )

    if _BEFORE_RE.search(user_text):
        if state.selected_invoice and state.selected_invoice in state.displayed_invoices:
            idx = state.displayed_invoices.index(state.selected_invoice)
            if idx > 0:
                return ReferenceResolution(
                    resolved_invoice=state.displayed_invoices[idx - 1],
                    matched_rule="relative_previous",
                )
            return ReferenceResolution(
                ambiguous_reason=f"no item precedes {state.selected_invoice} in the displayed list"
            )
        return ReferenceResolution(
            ambiguous_reason="relative 'before that' reference without a prior selected item in the displayed list"
        )

    if _NEXT_RE.search(user_text):
        if state.selected_invoice and state.selected_invoice in state.displayed_invoices:
            idx = state.displayed_invoices.index(state.selected_invoice)
            if idx + 1 < len(state.displayed_invoices):
                return ReferenceResolution(
                    resolved_invoice=state.displayed_invoices[idx + 1],
                    matched_rule="relative_next",
                )
            return ReferenceResolution(
                ambiguous_reason=f"no item follows {state.selected_invoice} in the displayed list"
            )
        return ReferenceResolution(
            ambiguous_reason="relative 'next' reference without a prior selected item in the displayed list"
        )

    phrase_match = _PHRASE_ONE_RE.search(user_text)
    candidate_phrase = phrase_match.group(1) if phrase_match else (
        user_text if state.unresolved_clarification and len(user_text.split()) <= 8 and "?" not in user_text else None
    )
    if candidate_phrase:
        if state.clarifying_options:
            opt_hits = _match_fragment_candidates(
                candidate_phrase, {opt: opt for opt in state.clarifying_options}
            )
            if len(opt_hits) == 1:
                chosen = opt_hits[0]
                if invs := _INVOICE_RE.findall(chosen):
                    return ReferenceResolution(resolved_invoice=invs[0], matched_rule="clarification_option_invoice")
                # Check whether the option maps uniquely to one displayed invoice snippet
                snip_hits = _match_fragment_candidates(chosen, state.invoice_snippets)
                if len(snip_hits) == 1:
                    return ReferenceResolution(
                        resolved_invoice=snip_hits[0],
                        resolved_vendor=chosen,
                        matched_rule="clarification_option_and_snippet",
                    )
                return ReferenceResolution(resolved_vendor=chosen, matched_rule="clarification_option_vendor")
        snip_hits = _match_fragment_candidates(candidate_phrase, state.invoice_snippets)
        if len(snip_hits) == 1:
            return ReferenceResolution(resolved_invoice=snip_hits[0], matched_rule="descriptor_snippet_match")
        if len(snip_hits) > 1:
            return ReferenceResolution(
                ambiguous_reason=(
                    f"'{candidate_phrase.strip()}' matches multiple displayed invoices: {', '.join(snip_hits)}"
                )
            )
        if phrase_match and not state.displayed_invoices and not state.clarifying_options:
            return ReferenceResolution(
                ambiguous_reason=f"'{candidate_phrase.strip()}' has no matching list or option in prior replies"
            )

    if _PLURAL_REF_RE.search(user_text):
        if len(state.displayed_invoices) >= 2:
            return ReferenceResolution(matched_rule="plural_displayed_list", is_plural_displayed=True)
        if state.selected_invoice:
            return ReferenceResolution(
                ambiguous_reason="plural reference used when only one invoice is in focus"
            )
        return ReferenceResolution(
            ambiguous_reason="plural reference with fewer than two items previously displayed"
        )

    if _SINGULAR_REF_RE.search(user_text):
        if state.selected_invoice:
            return ReferenceResolution(resolved_invoice=state.selected_invoice, matched_rule="selected_invoice")
        if len(state.displayed_invoices) == 1:
            return ReferenceResolution(
                resolved_invoice=state.displayed_invoices[0], matched_rule="single_displayed_invoice"
            )
        if len(state.displayed_invoices) > 1:
            return ReferenceResolution(
                ambiguous_reason=(
                    f"singular reference is ambiguous among {len(state.displayed_invoices)} displayed invoices "
                    f"({', '.join(state.displayed_invoices)})"
                )
            )
        if state.selected_vendor and not re.search(r"\b(?:bill|invoice)\b", user_text, re.I):
            return ReferenceResolution(resolved_vendor=state.selected_vendor, matched_rule="selected_vendor")
        return ReferenceResolution(ambiguous_reason="singular reference with no clear referent from earlier turns")

    return ReferenceResolution()


def _has_new_entity_tokens(user_text: str, prior_state: DialogueState) -> bool:
    """True when `user_text` appears to name a new capitalized vendor/topic not in prior state."""
    month_words = {
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
        "What", "How", "And", "Same", "As", "Of", "In", "On", "For", "If",
        "USD", "CAD", "EUR", "GBP", "AUD",
    }
    prior_blob = " ".join(
        prior_state.displayed_invoices
        + list(prior_state.invoice_snippets.values())
        + prior_state.clarifying_options
        + ([prior_state.selected_vendor] if prior_state.selected_vendor else [])
    ).lower()
    for tok in re.findall(r"\b[A-Z][A-Za-z0-9&'.-]{2,}\b", user_text):
        if tok in month_words:
            continue
        if tok.lower() not in prior_blob:
            return True
    return False


def update_dialogue_state(state: DialogueState, user_text: str, assistant_text: str) -> DialogueState:
    """Advance DialogueState after one completed user/assistant exchange."""
    nxt = state.clone()
    nxt.turn_count += 1
    res = resolve_reference(state, user_text)
    explicit_invs = list(dict.fromkeys(_INVOICE_RE.findall(user_text)))
    is_followup = _has_followup_marker(user_text, state) or bool(
        res.resolved_invoice or res.resolved_vendor or res.is_plural_displayed
    )
    shifted_entity_followup = (
        _FOLLOWUP_START_RE.search(user_text) is not None
        and not res.resolved_invoice
        and not res.resolved_vendor
        and not res.is_plural_displayed
        and _has_new_entity_tokens(user_text, state)
    )

    if (not is_followup or shifted_entity_followup) and state.turn_count > 0:
        # Standalone topic or new-entity branch: clear stale prior selections unless restated.
        nxt.displayed_invoices = []
        nxt.invoice_snippets = {}
        nxt.clarifying_options = []
        nxt.selected_invoice = None
        nxt.selected_vendor = None
        if not is_followup:
            nxt.date_filter = None
            nxt.currency_filter = None
            nxt.status_filter = None
        nxt.unresolved_clarification = None

    date_f, curr_f, stat_f = _extract_filters(user_text)
    if date_f is not None:
        nxt.date_filter = date_f
    if curr_f is not None:
        nxt.currency_filter = curr_f
    if stat_f is not None:
        nxt.status_filter = stat_f

    if res.resolved_invoice:
        nxt.selected_invoice = res.resolved_invoice
    elif len(explicit_invs) > 1:
        nxt.selected_invoice = None
    if res.resolved_vendor:
        nxt.selected_vendor = res.resolved_vendor

    disp_invs, snippets = extract_displayed_invoices(assistant_text)
    _, clarify_q = _body_lines_from_displayed(assistant_text)
    if len(disp_invs) >= 2:
        nxt.displayed_invoices = disp_invs
        nxt.invoice_snippets = snippets
        # Multiple invoices listed: keep selection only if this turn targeted a single item inside the new list.
        if nxt.selected_invoice not in disp_invs:
            nxt.selected_invoice = None
    elif len(disp_invs) == 1:
        inv = disp_invs[0]
        if is_followup and inv in nxt.displayed_invoices:
            # Single-item follow-up inside an active displayed list preserves the list for relative navigation.
            nxt.invoice_snippets[inv] = snippets[inv]
        elif not is_followup or not nxt.displayed_invoices:
            nxt.displayed_invoices = disp_invs
            nxt.invoice_snippets = snippets
        else:
            nxt.displayed_invoices = disp_invs
            nxt.invoice_snippets = snippets
        nxt.selected_invoice = inv

    nxt.unresolved_clarification = clarify_q
    nxt.clarifying_options = extract_clarifying_options(clarify_q)
    return nxt


def derive_dialogue_state(history: list) -> DialogueState:
    """Deterministically reconstruct DialogueState across a list of Turn(user, assistant)."""
    state = DialogueState()
    for t in history:
        state = update_dialogue_state(state, t.user, t.assistant)
    return state


def format_state_block(state: DialogueState, current_question: str) -> str | None:
    """Format a compact CONVERSATION STATE block when `current_question` continues prior state."""
    if state.turn_count == 0:
        return None
    res = resolve_reference(state, current_question)
    resolved_from_state = (
        (res.resolved_invoice is not None and res.matched_rule != "explicit_invoice")
        or res.resolved_vendor is not None
        or res.is_plural_displayed
        or res.ambiguous_reason is not None
    )
    shifted_followup = (
        _FOLLOWUP_START_RE.search(current_question) is not None
        and _has_new_entity_tokens(current_question, state)
    )
    continues_prior = resolved_from_state or (
        _has_followup_marker(current_question, state) and not shifted_followup
    )
    if not continues_prior:
        return None
    lines: list[str] = ["CONVERSATION STATE (derived from displayed turns only)"]
    if state.displayed_invoices:
        ordered = ", ".join(f"{i + 1}) {inv}" for i, inv in enumerate(state.displayed_invoices[:12]))
        lines.append(f"- Last displayed ordered invoice list: {ordered}")
    if state.selected_invoice:
        lines.append(f"- Currently selected invoice: {state.selected_invoice}")
    if state.selected_vendor:
        lines.append(f"- Currently selected vendor: {state.selected_vendor}")
    filters = [
        f"{k}={v}"
        for k, v in (
            ("date", state.date_filter),
            ("currency", state.currency_filter),
            ("status", state.status_filter),
        )
        if v
    ]
    if filters:
        lines.append("- Active filters: " + ", ".join(filters))
    if state.unresolved_clarification:
        lines.append(f"- Pending clarification from last turn: {state.unresolved_clarification}")
    if res.resolved_invoice:
        lines.append(f"- Resolved reference in current question: invoice {res.resolved_invoice} ({res.matched_rule})")
    elif res.resolved_vendor:
        lines.append(f"- Resolved reference in current question: vendor {res.resolved_vendor} ({res.matched_rule})")
    elif res.is_plural_displayed:
        lines.append(
            "- Resolved reference in current question: displayed invoices "
            + ", ".join(state.displayed_invoices)
        )
    elif res.ambiguous_reason:
        lines.append(
            f"- Unresolved ambiguity: {res.ambiguous_reason}. Do not guess; reply CLARIFY with one short question."
        )
    return "\n".join(lines)


def retrieval_query_terms(state: DialogueState, current_question: str) -> str:
    """Return justified resolved reference terms to aid BM25 retrieval in follow-up turns.

    Only emits terms that are deterministically resolved from displayed state; leaves
    ambiguous references unexpanded so retrieval does not fabricate a target.
    """
    if state.turn_count == 0:
        return current_question
    res = resolve_reference(state, current_question)
    if res.ambiguous_reason:
        return current_question
    extras: list[str] = []
    if res.resolved_invoice:
        extras.append(res.resolved_invoice)
        if snip := state.invoice_snippets.get(res.resolved_invoice):
            extras.append(snip)
    elif res.is_plural_displayed:
        extras.extend(state.displayed_invoices[:8])
    elif res.resolved_vendor:
        extras.append(res.resolved_vendor)
    elif _FOLLOWUP_START_RE.search(current_question) and not _has_new_entity_tokens(current_question, state):
        if state.selected_invoice:
            extras.append(state.selected_invoice)
        elif state.displayed_invoices:
            extras.extend(state.displayed_invoices[:4])
        if state.selected_vendor:
            extras.append(state.selected_vendor)
    if not extras:
        return current_question
    return current_question + " " + " ".join(extras)
