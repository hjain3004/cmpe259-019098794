"""Explicitly scripted UI rehearsal. Never used as a substitute for live results."""

from cashbooks.llm.scripted import ScriptedLLM
from cashbooks.llm.base import Message


class RehearsalLLM(ScriptedLLM):
    """Match only the current question, not entity names in retrieved context."""

    @staticmethod
    def _question_only(messages):
        if not messages:
            return messages
        last = messages[-1]
        question = last.text.rsplit("QUESTION\n", 1)[-1]
        return [*messages[:-1], Message(last.role, question)]

    def complete(self, system, messages, json_schema=None):
        return super().complete(system, self._question_only(messages), json_schema)

    def complete_with_tools(self, system, messages, tools, call_tool, max_calls=6):
        return super().complete_with_tools(system, self._question_only(messages), tools, call_tool, max_calls)


def rehearsal_llm() -> ScriptedLLM:
    evidence = lambda eid, supports: {"evidence_id": eid, "supports": supports}
    paid = {
        "answerability": "ANSWER",
        "answer": "Yes. Invoice NS-1048 for $842.00 USD was paid in full on September 12, 2026. The remaining balance is $0.00 USD.",
        "as_of": "2026-09-24",
        "evidence": [evidence("span_inv_NS-1048_total", "The invoice total is $842.00 USD."),
                     evidence("txn_0193", "The bank records the matching $842.00 USD debit.")],
    }
    return RehearsalLLM(
        replies={
            "What date was it paid": {
                **paid, "answer": "NS-1048 was paid on September 12, 2026, according to the matching bank transaction."
            },
            "NS-1048": paid,
            "BW-771": {
                "answerability": "WARN", "as_of": "2026-09-24",
                "answer": "Yes. The bank details on BW-771 differ from the trusted vendor record. The invoice lists an account ending in 5507. The account on file ends in 4417.",
                "evidence": [evidence("span_inv_BW-771_remit_account", "The invoice lists an account ending in 5507."),
                             evidence("vh_v_beanworks", "The trusted vendor record lists an account ending in 4417.")],
                "risk_indicators": ["The invoice requests payment to a different bank account."],
                "next_step": "Contact the vendor using the trusted contact on file before making a payment.",
            },
            "next seven days": {
                "answerability": "ANSWER", "as_of": "2026-09-24",
                "answer": "Invoice NS-1062 is due on October 1, 2026. Its remaining balance is $1,073.25 USD after the $45.00 USD credit.",
                "evidence": [evidence("span_inv_NS-1062_stated_due_date", "The invoice is due on October 1, 2026."),
                             evidence("span_cn_CN-0457_total", "A $45.00 USD credit applies to this bill.")],
            },
            "Pay it now": {
                "answerability": "ABSTAIN", "as_of": "2026-09-24",
                "answer": "I can explain your bills and payment records, but I cannot initiate a payment or change any records.",
                "evidence": [],
                "next_step": "Use your normal payment process after checking the bill and the vendor's payment details.",
            },
        },
        tool_plan={
            "What date was it paid": [("get_bill_status", {"invoice_number": "NS-1048", "as_of": "2026-09-24"})],
            "NS-1048": [("get_bill_status", {"invoice_number": "NS-1048", "as_of": "2026-09-24"})],
            "BW-771": [("compare_vendor_payment_details", {"invoice_number": "BW-771"})],
            "next seven days": [("list_open_bills", {"as_of": "2026-09-24", "due_before": "2026-10-01"})],
        },
        default={
            "answerability": "ABSTAIN", "as_of": "2026-09-24", "evidence": [],
            "answer": "This is an offline rehearsal with scripted examples. Use one of the suggested questions, or start the server in live mode to ask Claude a new question.",
        },
    )
