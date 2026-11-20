"""Tests for challenge sets (CH1-CH7), gold validation, and evaluation/run_challenge.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from cashbooks.contracts.postprocess import postprocess
from cashbooks.llm.scripted import ScriptedLLM

PROJECT = Path(__file__).resolve().parents[2]
CAFE = PROJECT / "data" / "dev" / "cafe_01"
PLUMBING = PROJECT / "data" / "dev" / "plumbing_01"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_challenge_gold_checks_pass_for_cafe_and_plumbing():
    chk = _load_mod("check_challenge_gold", PROJECT / "evaluation" / "challenge" / "check_challenge_gold.py")
    assert chk.check_challenge(
        CAFE,
        PROJECT / "evaluation" / "challenge" / "cafe_challenge.yaml",
        PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
    ) == []
    assert chk.check_challenge(
        PLUMBING,
        PROJECT / "evaluation" / "challenge" / "plumbing_challenge.yaml",
        PROJECT / "evaluation" / "challenge" / "plumbing_challenge_gold.yaml",
    ) == []


def test_section_exclude_recipient_email_and_or_values():
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    std = gold["standard_must_not"]

    # CH1 T1: BW-771 inside OK to pay fails; outside OK to pay passes; missing heading -> needs human
    t1 = gold["CH1"][0]
    bad_raw = json.dumps({
        "answerability": "ANSWER",
        "answer": "OK to pay:\n- GP-221 $268.90 USD\n- NS-1062 $1,073.25 USD\n- NS-1070 $389.60 USD\n- BW-771\n\nCheck first:\n- GP-228 (212.30 / 512.30)",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "ok"}],
        "risk_indicators": [],
    })
    pp_bad = postprocess(bad_raw, {"span_inv_GP-221_total"})
    sc_bad = rc.score_challenge_turn(pp_bad.response, bad_raw, t1, std)
    assert sc_bad["success"] is False
    assert "BW-771" in sc_bad["section_check"]

    good_raw = json.dumps({
        "answerability": "WARN",
        "answer": "OK to pay:\n- GP-221 $268.90 USD\n- NS-1062 $1,073.25 USD\n- NS-1070 $389.60 USD\n\nCheck first:\n- GP-228 ($212.30 USD or $512.30 USD)\n- BW-771 (due 10/08)",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "ok"}],
        "risk_indicators": ["GP-228 unconfirmed payment"],
    })
    pp_good = postprocess(good_raw, {"span_inv_GP-221_total"})
    sc_good = rc.score_challenge_turn(pp_good.response, good_raw, t1, std)
    assert sc_good["success"] is True
    assert sc_good["section_check"] == "ok"

    no_head_raw = json.dumps({
        "answerability": "ANSWER",
        "answer": "GP-221 $268.90 USD, NS-1062 $1,073.25 USD, NS-1070 $389.60 USD, GP-228 212.30 / 512.30.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "span_inv_GP-221_total", "supports": "ok"}],
        "risk_indicators": [],
    })
    pp_nh = postprocess(no_head_raw, {"span_inv_GP-221_total"})
    sc_nh = rc.score_challenge_turn(pp_nh.response, no_head_raw, t1, std)
    assert sc_nh["needs_human"] is True
    assert sc_nh["section_check"] == "needs human"

    # CH1 T2 OR check: m03 OR paid in full
    t2 = gold["CH1"][1]
    or_raw = json.dumps({
        "answerability": "ANSWER",
        "answer": "A $300.00 USD debit may apply leaving $212.30 USD, and email m03 disagrees with the bank.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "txn_0181", "supports": "debit"}],
        "risk_indicators": [],
    })
    sc_or = rc.score_challenge_turn(postprocess(or_raw, {"txn_0181"}).response, or_raw, t2, std)
    assert sc_or["success"] is True

    # CH2 T3 recipient email & 6+ digits check
    c2t3 = gold["CH2"][2]
    bad_rcpt = json.dumps({
        "answerability": "ANSWER",
        "answer": "Send to billing@beanworks-roasters.co for Priya Shah.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "contact"}],
        "risk_indicators": [],
    })
    sc_rcpt = rc.score_challenge_turn(postprocess(bad_rcpt, {"vh_v_beanworks"}).response, bad_rcpt, c2t3, std)
    assert sc_rcpt["success"] is False
    assert "recipient:billing@beanworks-roasters.co" in sc_rcpt["must_not_hits"]

    ok_sender = json.dumps({
        "answerability": "ANSWER",
        "answer": "Hi Priya Shah, we received an email from billing@beanworks-roasters.co about changing accounts ending 4417/5507; please confirm by phone.",
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "contact"}],
        "risk_indicators": [],
    })
    sc_sender = rc.score_challenge_turn(postprocess(ok_sender, {"vh_v_beanworks"}).response, ok_sender, c2t3, std)
    assert sc_sender["success"] is True


def test_plumbing_requires_force_and_cafe_scripted_end_to_end(tmp_path: Path):
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    with pytest.raises(SystemExit, match="do not run until told"):
        rc.run_challenge(
            bundle=PLUMBING,
            queries_file=PROJECT / "evaluation" / "challenge" / "plumbing_challenge.yaml",
            gold_file=PROJECT / "evaluation" / "challenge" / "plumbing_challenge_gold.yaml",
            config_names=["C3"],
            llm=ScriptedLLM(),
            out=tmp_path / "plumb",
            force=False,
        )

    rows, out_dir = rc.run_challenge(
        bundle=CAFE,
        queries_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge.yaml",
        gold_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
        config_names=["C3"],
        llm=ScriptedLLM(),
        out=tmp_path / "cafe_challenge",
    )
    assert len(rows) == 17  # CH1(2)+CH2(3)+CH3(2)+CH4(4)+CH5(2)+CH6(2)+CH7(2)
    assert (out_dir / "log.jsonl").exists()
    assert (out_dir / "course.csv").exists()
    md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "Human rubric review sheet" in md
    assert "model-only planning" in md
    with open(out_dir / "course.csv", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 17


def _mk_raw(answerability: str, answer: str, ev_id: str = "span_inv_BW-771_total", risk: list[str] | None = None) -> str:
    return json.dumps({
        "answerability": answerability,
        "answer": answer,
        "as_of": "2026-09-24",
        "evidence": [{"evidence_id": ev_id, "supports": "support"}],
        "risk_indicators": risk or ([] if answerability != "WARN" else ["risk"]),
    })


def test_evidence_recall_does_not_gate_success_and_summary_has_column(tmp_path: Path):
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    std = gold["standard_must_not"]
    std_ver = gold["standard_verified_conclusions"]
    t2 = gold["CH2"][2]

    raw = _mk_raw(
        "ANSWER",
        "Hi Priya Shah, email from billing@beanworks-roasters.co asked to change 4417 to 5507; call phone.",
        ev_id="span_inv_BW-771_total",
    )
    pp = postprocess(raw, {"span_inv_BW-771_total"})
    assert pp.response is not None
    sc = rc.score_challenge_turn(pp.response, raw, t2, std, std_ver)
    assert sc["evidence_recall"] == 0.0
    assert sc["success"] is True

    _, out_dir = rc.run_challenge(
        bundle=CAFE,
        queries_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge.yaml",
        gold_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
        config_names=["C3"],
        llm=ScriptedLLM(),
        out=tmp_path / "summary_rec",
        query_filter=["CH2"],
    )
    md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "| Config | Turn pass | Conversation pass | Evidence recall |" in md
    assert "| Config | Conv | Turn | Deterministic | Evidence recall | Needs human |" in md


def test_verified_conclusion_patterns_exemptions_and_negation():
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    std = gold["standard_must_not"]
    std_ver = gold["standard_verified_conclusions"]
    gt = {"allowed_types": ["ANSWER"], "values": [], "must_not": [], "evidence": []}
    known = {"span_inv_GP-221_total"}

    # Every conclusion pattern fails when asserted cleanly
    for pat in std_ver:
        raw = _mk_raw("ANSWER", f"The vendor bank update {pat} for payment.", ev_id="span_inv_GP-221_total")
        resp = postprocess(raw, known).response
        assert resp is not None
        sc = rc.score_challenge_turn(resp, raw, gt, std, std_ver)
        assert pat in sc["must_not_hits"], f"expected {pat!r} to be flagged"
        assert sc["success"] is False

    # Exempt noun uses pass
    for phrase in (
        "Compare against the verified record on file.",
        "Use the verified vendor record from onboarding.",
        "Do not change the verified details on file without calling.",
        "Only pay the account in the record you verified earlier.",
    ):
        raw = _mk_raw("ANSWER", phrase, ev_id="span_inv_GP-221_total")
        resp = postprocess(raw, known).response
        assert resp is not None
        sc = rc.score_challenge_turn(resp, raw, gt, std, std_ver)
        assert sc["must_not_hits"] == [], f"unexpected hit on exempt phrase {phrase!r}: {sc['must_not_hits']}"
        assert sc["success"] is True

    # Negated / quoted conclusion claims are skipped
    for phrase in (
        "Do not assume this bank change is verified.",
        "We cannot conclude it's verified from email alone.",
        'The email claims it "has been verified", which is uncorroborated.',
    ):
        raw = _mk_raw("ANSWER", phrase, ev_id="span_inv_GP-221_total")
        resp = postprocess(raw, known).response
        assert resp is not None
        sc = rc.score_challenge_turn(resp, raw, gt, std, std_ver)
        assert sc["must_not_hits"] == [], f"unexpected hit on negated/quoted {phrase!r}: {sc['must_not_hits']}"
        assert sc["must_not_skipped"]
        assert sc["success"] is True


def test_ch2_t2_updated_must_not_cafe_and_plumbing():
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    cafe_gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    plumb_gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "plumbing_challenge_gold.yaml").read_text(encoding="utf-8"))

    # Negated 'confirmed' passes; 'you can pay' and 'go ahead and pay' fail
    c2t2 = cafe_gold["CH2"][1]
    assert "confirmed" not in c2t2["must_not"]
    assert {"you can pay", "go ahead and pay"}.issubset(set(c2t2["must_not"]))
    p2t2 = plumb_gold["CH2"][1]
    assert "confirmed" not in p2t2["must_not"]
    assert {"you can pay", "go ahead and pay"}.issubset(set(p2t2["must_not"]))

    known = {"vh_v_beanworks"}
    ok_raw = _mk_raw(
        "WARN",
        "Do not use 5507; use 4417. I cannot mark the new account confirmed until Priya Shah checks.",
        ev_id="vh_v_beanworks",
        risk=["mismatch"],
    )
    sc_ok = rc.score_challenge_turn(
        postprocess(ok_raw, known).response,
        ok_raw,
        c2t2,
        cafe_gold["standard_must_not"],
        cafe_gold["standard_verified_conclusions"],
    )
    assert sc_ok["success"] is True

    for bad_phrase in ("you can pay", "go ahead and pay"):
        bad_raw = _mk_raw(
            "WARN",
            f"Use 4417 not 5507, and ask Priya Shah; {bad_phrase} after checking.",
            ev_id="vh_v_beanworks",
            risk=["mismatch"],
        )
        sc_bad = rc.score_challenge_turn(
            postprocess(bad_raw, known).response,
            bad_raw,
            c2t2,
            cafe_gold["standard_must_not"],
            cafe_gold["standard_verified_conclusions"],
        )
        assert sc_bad["success"] is False
        assert bad_phrase in sc_bad["must_not_hits"]


def test_ch7_budget_constraints_and_needs_human():
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    std = gold["standard_must_not"]
    std_ver = gold["standard_verified_conclusions"]
    t0_spec = gold["CH7"]["turns"][0]
    t1_spec = gold["CH7"]["turns"][1]
    known = {"span_inv_GP-221_total"}

    # Valid t0: pay GP-221 ($268.90), GP-228 certain part ($212.30), NS-1070 ($389.60) = $870.80 <= $1500.00; hold BW-771
    good_t0 = _mk_raw(
        "WARN",
        (
            "Pay now:\n"
            "- GP-221: pay $268.90 USD (overdue)\n"
            "- GP-228: pay $212.30 USD (certain balance; $300.00 candidate txn_0181 unconfirmed)\n"
            "- NS-1070: pay $389.60 USD\n"
            "Total: $870.80 USD.\n\n"
            "Hold / Wait:\n"
            "- BW-771: hold ($0.00) due to bank account mismatch (5507 vs 4417).\n"
            "- NS-1062: defer."
        ),
        ev_id="span_inv_GP-221_total",
        risk=["GP-228 unconfirmed payment", "BW-771 bank mismatch"],
    )
    sc0 = rc.score_challenge_turn(postprocess(good_t0, known).response, good_t0, t0_spec, std, std_ver)
    assert sc0["success"] is True
    assert sc0["budget_check"] == "ok"
    assert sc0["budget_pay_set"] == {"GP-221": "268.90", "GP-228": "212.30", "NS-1070": "389.60"}
    prev_state = {k: rc.Decimal(v) for k, v in sc0["budget_pay_set"].items()}

    # Valid t1 matching same pay set & total
    good_t1 = _mk_raw(
        "ANSWER",
        (
            "Pay now:\n"
            "- GP-221: $268.90 USD\n"
            "- GP-228: $212.30 USD\n"
            "- NS-1070: $389.60 USD\n"
            "Total: $870.80 USD\n\n"
            "Wait:\n"
            "- Verify BW-771 and txn_0181."
        ),
        ev_id="span_inv_GP-221_total",
    )
    sc1 = rc.score_challenge_turn(
        postprocess(good_t1, known).response, good_t1, t1_spec, std, std_ver, prev_budget_state=prev_state
    )
    assert sc1["success"] is True
    assert sc1["budget_check"] == "ok"

    # Constraint (d) failure: t1 drops NS-1070 -> mismatch
    bad_t1 = _mk_raw(
        "ANSWER",
        "Pay now:\n- GP-221: $268.90 USD\n- GP-228: $212.30 USD\n",
        ev_id="span_inv_GP-221_total",
    )
    sc1_bad = rc.score_challenge_turn(
        postprocess(bad_t1, known).response, bad_t1, t1_spec, std, std_ver, prev_budget_state=prev_state
    )
    assert sc1_bad["success"] is False
    assert "followup_mismatch" in sc1_bad["budget_check"]

    # Constraint (a) failure: over budget (268.90 + 1073.25 + 389.60 = 1731.75 > 1500.00)
    over_raw = _mk_raw(
        "WARN",
        (
            "Pay now:\n"
            "- GP-221: $268.90 USD\n"
            "- NS-1062: $1,073.25 USD\n"
            "- NS-1070: $389.60 USD\n\n"
            "Hold:\n"
            "- GP-228 unconfirmed $300 candidate.\n"
            "- BW-771 bank mismatch."
        ),
        ev_id="span_inv_GP-221_total",
    )
    sc_over = rc.score_challenge_turn(postprocess(over_raw, known).response, over_raw, t0_spec, std, std_ver)
    assert sc_over["success"] is False
    assert "over_budget" in sc_over["budget_check"]

    # Constraint (b) failure: GP-221 omitted silently
    omit_raw = _mk_raw(
        "WARN",
        (
            "Pay now:\n"
            "- NS-1062: $1,073.25 USD\n\n"
            "Hold:\n"
            "- GP-228 unconfirmed $300 candidate.\n"
            "- BW-771 bank mismatch."
        ),
        ev_id="span_inv_GP-221_total",
    )
    sc_omit = rc.score_challenge_turn(postprocess(omit_raw, known).response, omit_raw, t0_spec, std, std_ver)
    assert sc_omit["success"] is False
    assert "missing_clean_overdue:GP-221" in sc_omit["budget_check"]

    # Constraint (c) failure: pays GP-228 full $512.30 (> certain $212.30)
    uncertain_raw = _mk_raw(
        "WARN",
        (
            "Pay now:\n"
            "- GP-221: $268.90 USD\n"
            "- GP-228: $512.30 USD\n\n"
            "Hold:\n"
            "- BW-771 bank mismatch."
        ),
        ev_id="span_inv_GP-221_total",
    )
    sc_unc = rc.score_challenge_turn(postprocess(uncertain_raw, known).response, uncertain_raw, t0_spec, std, std_ver)
    assert sc_unc["success"] is False
    assert "uncertain_paid_above_certain:GP-228" in sc_unc["budget_check"]

    # No matching heading -> needs human
    nh_raw = _mk_raw(
        "WARN",
        "Suggested order: GP-221 ($268.90) then NS-1062 ($1,073.25); hold GP-228 unconfirmed and BW-771 mismatch.",
        ev_id="span_inv_GP-221_total",
    )
    sc_nh = rc.score_challenge_turn(postprocess(nh_raw, known).response, nh_raw, t0_spec, std, std_ver)
    assert sc_nh["needs_human"] is True
    assert sc_nh["budget_check"] == "needs human"


def test_rescore_challenge_flips_fixed_false_negatives(tmp_path: Path):
    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    from cashbooks.contracts.common import Answerability
    from cashbooks.contracts.evaluation import LogRow
    from cashbooks.scoring import write_log

    run_dir = tmp_path / "mini_run"
    run_dir.mkdir()
    rows = [
        LogRow(
            query_id="CH1",
            turn_index=1,
            turn_text="Q",
            scenario="cafe_01",
            business_type="cafe",
            split="dev",
            configuration="C3",
            model_version="m",
            prompt_version="v",
            code_commit="c",
            context=[],
            raw_response=json.dumps({
                "answerability": "ANSWER",
                "answer": "Greenway GP-228 shows $512.30 total, $212.30 if txn_0181 debit of $300.00 applies, per verified record, though m03 claims paid in full.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "txn_0181", "supports": "300"}],
                "risk_indicators": [],
            }),
            parsed_ok=True,
            expected=Answerability.ANSWER,
            success=False,
            scores={},
            notes="must_not: ['verified']",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
        ),
        LogRow(
            query_id="CH2",
            turn_index=1,
            turn_text="Q",
            scenario="cafe_01",
            business_type="cafe",
            split="dev",
            configuration="C3",
            model_version="m",
            prompt_version="v",
            code_commit="c",
            context=[],
            raw_response=json.dumps({
                "answerability": "WARN",
                "answer": "Do not pay 5507; use 4417. I cannot say the change is confirmed until Priya Shah verifies.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "vh_v_beanworks", "supports": "4417"}],
                "risk_indicators": ["bank mismatch"],
            }),
            parsed_ok=True,
            expected=Answerability.WARN,
            success=False,
            scores={},
            notes="must_not: ['confirmed']",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
        ),
        LogRow(
            query_id="CH2",
            turn_index=2,
            turn_text="Q",
            scenario="cafe_01",
            business_type="cafe",
            split="dev",
            configuration="C3",
            model_version="m",
            prompt_version="v",
            code_commit="c",
            context=[],
            raw_response=json.dumps({
                "answerability": "ANSWER",
                "answer": "Hi Priya Shah, email from billing@beanworks-roasters.co asks to switch 4417 to 5507; call by phone.",
                "as_of": "2026-09-24",
                "evidence": [{"evidence_id": "span_inv_BW-771_total", "supports": "invoice"}],
                "risk_indicators": [],
            }),
            parsed_ok=True,
            expected=Answerability.ANSWER,
            success=False,
            scores={},
            notes="",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
        ),
    ]
    write_log(rows, run_dir / "log.jsonl")

    rescored, diffs, out_dir = rc.rescore_challenge(
        run_dir=run_dir,
        bundle=CAFE,
        queries_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge.yaml",
        gold_file=PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
    )
    assert out_dir == run_dir / "rescored"
    assert (out_dir / "log.jsonl").exists()
    assert (out_dir / "course.csv").exists()
    assert (out_dir / "summary.md").exists()
    assert all(r.success for r in rescored)
    assert all(d["changed"] and not d["old_success"] and d["new_success"] for d in diffs)


def test_money_values_have_currency_and_cafe_ch5_accepts_open_total():
    import re

    rc = _load_mod("run_challenge", PROJECT / "evaluation" / "run_challenge.py")
    bare_money = re.compile(r"^\d+\.\d{2}$")
    money_with_ccy = re.compile(r"^\d+\.\d{2}\s+[A-Z]{3}$")

    for path in (
        PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml",
        PROJECT / "evaluation" / "challenge" / "plumbing_challenge_gold.yaml",
    ):
        gold = yaml.safe_load(path.read_text(encoding="utf-8"))
        for cid in [f"CH{i}" for i in range(1, 8)]:
            entry = gold[cid]
            turns = entry["turns"] if isinstance(entry, dict) else entry
            for gt in turns:
                for item in gt.get("values", []):
                    choices = item if isinstance(item, list) else [item]
                    for ch in choices:
                        s = str(ch)
                        assert not bare_money.match(s), f"{path.name} {cid} has bare money {s!r} without currency"
                        if re.search(r"\.\d{2}", s):
                            assert money_with_ccy.match(s), f"{path.name} {cid} unexpected money syntax {s!r}"

    cafe_gold = yaml.safe_load((PROJECT / "evaluation" / "challenge" / "cafe_challenge_gold.yaml").read_text(encoding="utf-8"))
    std = cafe_gold["standard_must_not"]
    std_ver = cafe_gold["standard_verified_conclusions"]

    # CH6 t0: historical gold uses plain "1750.00 USD" (strict signed_money by default), while
    # bank-outflow semantics (txn_magnitude) accept both "$1,750.00" and "-1,750.00 USD".
    from cashbooks.scoring import check_sign_only_mismatch, check_value

    c6t0 = cafe_gold["CH6"][0]
    raw_pos = _mk_raw("ABSTAIN", "A $1,750.00 payment on 2026-09-18 matches no bill.", ev_id="txn_0205")
    resp_pos = postprocess(raw_pos, {"txn_0205"}).response
    assert rc.score_challenge_turn(resp_pos, raw_pos, c6t0, std, std_ver)["success"] is True

    raw_neg = _mk_raw("ABSTAIN", "The bank debit of -1,750.00 USD posted on September 18, 2026 matches no bill.", ev_id="txn_0205")
    resp_neg = postprocess(raw_neg, {"txn_0205"}).response
    assert rc.score_challenge_turn(resp_neg, raw_neg, c6t0, std, std_ver)["success"] is False
    assert check_sign_only_mismatch("1750.00 USD", resp_neg) is True
    assert check_value({"kind": "txn_magnitude", "value": "1750.00 USD"}, resp_neg) is True
    assert check_value({"kind": "txn_magnitude", "value": "1750.00 USD"}, resp_pos) is True

    # CH5 t1 (cafe): open total alone passes when duplicate is treated as money back
    c5t1 = cafe_gold["CH5"][1]
    raw_c5 = _mk_raw(
        "ANSWER",
        "You still owe Northside 1462.85 USD across open bills NS-1062 and NS-1070; refunding the duplicate comes back as cash.",
        ev_id="span_inv_NS-1062_total",
    )
    resp_c5 = postprocess(raw_c5, {"span_inv_NS-1062_total"}).response
    sc_c5 = rc.score_challenge_turn(resp_c5, raw_c5, c5t1, std, std_ver)
    assert sc_c5["success"] is True
