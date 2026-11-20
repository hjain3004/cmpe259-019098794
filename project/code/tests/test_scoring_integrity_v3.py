"""Focused regression tests for scorer_v3 money, currency, sign, and numeric boundary integrity."""

from __future__ import annotations

from cashbooks.contracts.common import Answerability
from cashbooks.contracts.response import AssistantResponse
from cashbooks.scoring import SCORER_VERSION, check_sign_only_mismatch, check_value, score_turn


def _resp(answer: str, *, calculation: dict | None = None, next_step: str | None = None) -> AssistantResponse:
    return AssistantResponse.model_validate(
        {
            "answerability": "ANSWER",
            "answer": answer,
            "as_of": "2026-09-24",
            "evidence": [{"evidence_id": "span_inv_NS-1062_total", "supports": "total"}],
            "calculation": calculation,
            "risk_indicators": [],
            "clarifying_question": None,
            "next_step": next_step,
        }
    )


def test_scorer_version_constant():
    assert SCORER_VERSION == "scorer_v3_1"


def test_confirmed_defect_42_vs_142_eur_and_numeric_boundaries():
    # Exact defect reported in assignment
    assert check_value("42.00 USD", _resp("The total is 142.00 EUR.")) is False
    # Same currency, still substring inside a larger number
    assert check_value("42.00 USD", _resp("The total is 142.00 USD.")) is False
    assert check_value("42.00 USD", _resp("The total is $1,042.00 USD.")) is False
    assert check_value("42.00 USD", _resp("The total is $42.50 USD.")) is False
    assert check_value("42.00 USD", _resp("The total is $42.005 USD.")) is False
    assert check_value("42.00 USD", _resp("Invoice INV-42 USD is open.")) is False
    # Exact bounded match succeeds
    assert check_value("42.00 USD", _resp("The total is $42.00 USD.")) is True
    assert check_value("42.00 USD", _resp("The total is 42.00 USD.")) is True


def test_usd_vs_eur_and_currency_enforcement():
    assert check_value("42.00 USD", _resp("The total is 42.00 EUR.")) is False
    assert check_value("42.00 USD", _resp("The total is €42.00.")) is False
    assert check_value("42.00 USD", _resp("The total is EUR 42.00.")) is False
    assert check_value("42.00 EUR", _resp("The total is $42.00 USD.")) is False
    assert check_value("42.00 EUR", _resp("The total is $42.00.")) is False
    assert check_value("42.00 EUR", _resp("The total is €42.00.")) is True
    assert check_value("42.00 EUR", _resp("The total is 42.00 EUR.")) is True
    assert check_value("42.00 EUR", _resp("The total is EUR €42.00.")) is True
    # Conflicting prefix/suffix or symbol/ISO on same mention
    assert check_value("42.00 USD", _resp("The total is EUR 42.00 USD.")) is False
    assert check_value("42.00 USD", _resp("The total is €42.00 USD.")) is False
    # Bare number without currency symbol or ISO code cannot satisfy a money expectation
    assert check_value("42.00 USD", _resp("The total is 42.00.")) is False
    assert check_value("42.00 EUR", _resp("The total is 42.00.")) is False


def test_positive_vs_negative_amounts():
    # Positive expected must reject negative mentions
    assert check_value("42.00 USD", _resp("The bank debit is -42.00 USD.")) is False
    assert check_value("42.00 USD", _resp("The bank debit is -$42.00 USD.")) is False
    assert check_value("42.00 USD", _resp("The bank debit is $-42.00 USD.")) is False
    assert check_value("42.00 USD", _resp("The bank debit is −$42.00 USD.")) is False
    # Spaced hyphen separator or parenthetical positive amount stays positive
    assert check_value("42.00 USD", _resp("GP-221 - $42.00 USD due tomorrow.")) is True
    assert check_value("42.00 USD", _resp("GP-221 ($42.00 USD) is unpaid.")) is True

    # Negative expected must require a negative sign
    assert check_value("-1750.00 USD", _resp("The bank row is 1,750.00 USD.")) is False
    assert check_value("-1750.00 USD", _resp("The bank row is $1,750.00 USD.")) is False
    assert check_value("-1750.00 USD", _resp("The bank row is -1,750.00 USD.")) is True
    assert check_value("-1750.00 USD", _resp("The bank row is -$1,750.00 USD.")) is True
    assert check_value("-1750.00 USD", _resp("The bank row is $-1,750.00 USD.")) is True
    assert check_value("-1750.00 USD", _resp("The bank row is USD -1,750.00.")) is True
    assert check_value("-1750.00 USD", _resp("The bank row is −1,750.00 USD.")) is True


def test_comma_separated_and_equivalent_decimal_formatting():
    assert check_value("1073.25 USD", _resp("Remaining balance: $1,073.25 USD.")) is True
    assert check_value("1073.25 USD", _resp("Remaining balance: 1,073.25 USD.")) is True
    assert check_value("1073.25 USD", _resp("Remaining balance: USD 1,073.25.")) is True
    assert check_value("42.00 USD", _resp("Total owed: $42 USD.")) is True
    assert check_value("42.00 USD", _resp("Total owed: 42 USD.")) is True
    assert check_value("42.00 USD", _resp("Total owed: $42.0 USD.")) is True
    assert check_value("42.50 USD", _resp("Total owed: $42.5 USD.")) is True
    assert check_value("1750.00 USD", _resp("Total owed: $1,750 USD.")) is True
    # Malformed comma grouping rejected
    assert check_value("123.00 USD", _resp("Total owed: $1,23.00 USD.")) is False
    # Zero balance
    assert check_value("0.00 USD", _resp("Remaining balance is $0.00 USD.")) is True
    assert check_value("0.00 USD", _resp("Remaining balance is $0 USD.")) is True


def test_structured_calculation_currency_integrity():
    # Correct amount and currency in calculation passes
    calc_usd = {"steps": ["20.00 + 22.00"], "result": {"amount": "42.00", "currency": "USD"}}
    assert check_value("42.00 USD", _resp("See calculation.", calculation=calc_usd)) is True

    # Correct structured amount with WRONG currency must fail when prose does not establish USD
    calc_eur = {"steps": ["20.00 + 22.00 = 42.00"], "result": {"amount": "42.00", "currency": "EUR"}}
    assert check_value("42.00 USD", _resp("The total is 42.00 EUR.", calculation=calc_eur)) is False
    assert check_value("42.00 USD", _resp("The total is 42.00.", calculation=calc_eur)) is False
    # Bare '$' cannot override a conflicting structured EUR calculation for the same amount
    assert check_value("42.00 USD", _resp("The total is $42.00.", calculation=calc_eur)) is False
    # Genuine multi-currency reply with explicit USD tag in prose still matches USD
    assert check_value("42.00 USD", _resp("You owe 42.00 EUR and 42.00 USD.", calculation=calc_eur)) is True


def test_ambiguous_and_unsupported_currencies():
    # Bare '$' never establishes non-USD dollar currencies
    assert check_value("42.00 CAD", _resp("The total is $42.00.")) is False
    assert check_value("42.00 AUD", _resp("The total is $42.00.")) is False
    # Explicit CAD / CA$ matches CAD and rejects USD
    assert check_value("42.00 CAD", _resp("The total is CA$42.00.")) is True
    assert check_value("42.00 CAD", _resp("The total is $42.00 CAD.")) is True
    assert check_value("42.00 USD", _resp("The total is $42.00 CAD.")) is False
    assert check_value("42.00 USD", _resp("The total is CA$42.00.")) is False
    # Bare '$' is rejected for USD when another dollar currency appears anywhere in the reply
    assert check_value("42.00 USD", _resp("All amounts are in CAD. Total is $42.00.")) is False
    assert check_value("42.00 USD", _resp("Invoice A is $10.00 AUD; Invoice B is $42.00.")) is False
    # Bare '$' within USD/EUR-only contract scope (no other dollar currency, no calc conflict)
    assert check_value("42.00 USD", _resp("You owe $42.00 and €100.00 EUR.")) is True
    # Ambiguous yen symbol requires explicit ISO code
    assert check_value("42.00 JPY", _resp("The total is ¥42.")) is False
    assert check_value("42.00 JPY", _resp("The total is ¥42 JPY.")) is True
    # Explicit GBP symbol and ISO
    assert check_value("42.00 GBP", _resp("The total is £42.00.")) is True
    assert check_value("42.00 USD", _resp("The total is £42.00.")) is False


def test_bare_number_boundaries_and_commas():
    assert check_value("42", _resp("Count is 42.50 bags.")) is False
    assert check_value("42", _resp("Count is 1,042 bags.")) is False
    assert check_value("42", _resp("Balance is -42.")) is False
    assert check_value("42", _resp("Balance is -$42.")) is False
    assert check_value("42", _resp("Invoice INV-42 is open.")) is False
    assert check_value("42", _resp("Count is 42.")) is True
    assert check_value("1250.00", _resp("Amount is $1,250.00.")) is True
    assert check_value("6611", _resp("Account ending ****6611.")) is True
    assert check_value("-1750.00", _resp("Debit of -1,750.00 posted.")) is True
    assert check_value("-1750.00", _resp("Debit of 1,750.00 posted.")) is False


def test_score_turn_fails_on_currency_mismatch():
    sc = score_turn(
        _resp("The total is 142.00 EUR."),
        Answerability.ANSWER,
        {"total": "42.00 USD"},
        ["inv_NS-1062"],
        [],
    )
    assert sc.values == {"total": False}
    assert sc.success is False


def test_scoped_currency_declarations_positive_and_negative():
    # Explicit unambiguous scoped declarations establish currency for SUBSEQUENT amounts
    assert check_value("268.90 USD", _resp("Open bills (all USD):\n- GP-221: 268.90\n- NS-1062: 1,073.25")) is True
    assert check_value("1073.25 USD", _resp("Open bills (all USD):\n- GP-221: 268.90\n- NS-1062: 1,073.25")) is True
    assert check_value("42.00 EUR", _resp("All amounts are in EUR:\n- Invoice A: 42.00")) is True
    assert check_value("42.00 CAD", _resp("All amounts in CAD. Total is $42.00.")) is True
    assert check_value("42.00 GBP", _resp("Currency: GBP. Remaining: 42.00.")) is True

    # Must NOT apply retroactively to amounts before the declaration
    assert check_value("42.00 USD", _resp("Total is 42.00. (All amounts in USD.)")) is False

    # Numeric boundaries and strict sign rules STILL apply inside scoped currency
    assert check_value("42.00 USD", _resp("All amounts in USD. Total is 142.00.")) is False
    assert check_value("42.00 USD", _resp("All amounts in USD. Balance is -42.00.")) is False

    # Compound / ambiguous declarations must NOT silently pass
    assert check_value("42.00 USD", _resp("All amounts in USD or EUR. Total is 42.00.")) is False
    assert check_value("42.00 USD", _resp("All amounts in USD and EUR. Total is 42.00.")) is False
    assert check_value("42.00 USD", _resp("Currency: USD, EUR. Total is 42.00.")) is False
    assert check_value("42.00 USD", _resp("All amounts in USD/EUR. Total is 42.00.")) is False

    # Contradictory declarations must NOT silently pass
    assert check_value("42.00 USD", _resp("All amounts in USD. All amounts in EUR. Total is 42.00.")) is False

    # Contaminated scope (another currency explicitly mentioned inside scope) must NOT pass bare amounts
    assert check_value("42.00 USD", _resp("All amounts in USD. Invoice A is 100.00 EUR; Invoice B is 42.00.")) is False
    assert check_value("42.00 EUR", _resp("All amounts in EUR. Invoice A is $10.00; Invoice B is 42.00.")) is False

    # Explicit mention-level currency conflict always overrides scope and rejects
    assert check_value("42.00 USD", _resp("All amounts in USD. Total is 42.00 EUR.")) is False
    assert check_value("42.00 USD", _resp("All amounts in USD. Total is €42.00.")) is False

    # Conflicting structured calculation currency blocks scoped bare fallback for the same amount
    calc_eur = {"steps": ["42.00"], "result": {"amount": "42.00", "currency": "EUR"}}
    assert check_value("42.00 USD", _resp("All amounts in USD. Total is 42.00.", calculation=calc_eur)) is False


def test_amount_semantics_signed_balance_vs_txn_magnitude_vs_non_money():
    debit_resp = _resp("Bank debit txn_6006 posted for -550.00 USD.")
    pos_resp = _resp("Bank payment txn_6006 was $550.00 USD.")
    wrong_ccy = _resp("Bank debit txn_6006 posted for -550.00 EUR.")
    wrong_mag = _resp("Bank debit txn_6006 posted for -1,550.00 USD.")

    # Default signed_money stays strict: positive balance rejects negative debit
    assert check_value("550.00 USD", debit_resp) is False
    assert check_value("550.00 USD", pos_resp) is True
    # Actual sign error on expected negative balance stays strict
    assert check_value("-550.00 USD", pos_resp) is False

    # Explicit txn_magnitude accepts BOTH positive magnitude and negative statement debit
    mag_spec = {"kind": "txn_magnitude", "value": "550.00 USD"}
    assert check_value(mag_spec, debit_resp) is True
    assert check_value(mag_spec, pos_resp) is True
    assert check_value("550.00 USD", debit_resp, amount_semantics="txn_magnitude") is True
    # Still strictly enforces currency and numeric boundaries!
    assert check_value(mag_spec, wrong_ccy) is False
    assert check_value(mag_spec, wrong_mag) is False
    assert check_value(mag_spec, _resp("Bank debit posted for -550.00.")) is False

    # score_turn supports typed spec dicts directly
    sc = score_turn(debit_resp, Answerability.ANSWER, {"amount": mag_spec}, ["inv_NS-1062"], [])
    assert sc.values == {"amount": True}
    assert sc.success is True

    # Non-money bare number stays strict by default, and supports explicit txn_magnitude if declared
    assert check_value("300.00", _resp("Debit of -300.00 USD.")) is False
    assert check_value({"kind": "txn_magnitude", "value": "300.00"}, _resp("Debit of -300.00 USD.")) is True
    assert check_value({"kind": "non_money_number", "value": "12"}, _resp("12 bags.")) is True
    assert check_value({"kind": "non_money_number", "value": "12"}, _resp("-12 bags.")) is False


def test_sign_only_mismatch_routes_policy_review_not_real_errors():
    debit_resp = _resp("Bank debit txn_6006 posted for -550.00 USD.")
    wrong_ccy = _resp("Bank debit txn_6006 posted for -550.00 EUR.")
    wrong_mag = _resp("Bank debit txn_6006 posted for -1,550.00 USD.")
    pos_resp = _resp("Bank payment txn_6006 was $550.00 USD.")

    # Positive unannotated money failing ONLY because reply wrote negative debit -> routed to review
    assert check_sign_only_mismatch("550.00 USD", debit_resp) is True
    assert check_sign_only_mismatch("300.00", _resp("Debit of -300.00 USD.")) is True
    # Wrong currency or wrong magnitude -> real failure, NOT sign-only review
    assert check_sign_only_mismatch("550.00 USD", wrong_ccy) is False
    assert check_sign_only_mismatch("550.00 USD", wrong_mag) is False
    # Already passing or already declared txn_magnitude -> False
    assert check_sign_only_mismatch("550.00 USD", pos_resp) is False
    assert check_sign_only_mismatch({"kind": "txn_magnitude", "value": "550.00 USD"}, debit_resp) is False
    # Expected negative balance failing against positive prose -> actual sign error, NOT debit ambiguity
    assert check_sign_only_mismatch("-550.00 USD", pos_resp) is False
