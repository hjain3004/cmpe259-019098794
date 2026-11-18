"""Run the frozen invoice-header extraction on real scanned receipts (SROIE, ICDAR 2019)
and on the synthetic café invoices, and score the fields both share: vendor name,
date and total.

The question is the one from the check-in 1 feedback: does extraction accuracy on the
synthetic invoices hold up on real documents? Same prompt, same schema, same model.

    cd project
    git clone --depth 1 https://github.com/zzzDavid/ICDAR-2019-SROIE.git data/real/sroie_src
    python evaluation/real_docs_check.py data/real/sroie_src/data --synthetic data/dev/cafe_01

Receipts are read from the dataset's own transcripts (data/box), so no images are
sent anywhere. Only aggregate scores and receipt IDs go to evaluation/results/; the
per-receipt values stay in data/real/runs/, which is not committed.

Each field is scored twice:
    read        the model copied the right value (dates compared day-first, the
                receipts' own convention)
    normalized  the pipeline's own normalizer then turns it into the right value
                (the café pipeline parses dates month-first, as US invoices print them)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cashbooks.contracts.extraction import InvoiceHeaderExtraction
from cashbooks.extract import pipeline
from cashbooks.extract.pipeline import call_schema
from cashbooks.ingest.pdf_text import find_span
from cashbooks.normalize.dates import AmbiguousDateError, DateParseError, parse_date
from cashbooks.normalize.money import MoneyParseError, parse_amount

PROJECT = Path(__file__).resolve().parents[1]
PROMPT = "extract_invoice_header_v1.md"
FIELDS = ("vendor", "date", "total")

# ---------------------------------------------------------------- normalizers used only for scoring

_DMY = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d/%b/%y", "%d %b %y", "%b %d, %Y",
        "%B %d, %Y", "%d%b%Y", "%Y%m%d", "%d%m%Y",
        "%m/%d/%Y", "%m/%d/%y"]  # month-first last: only when day-first is impossible (12/28/2017)


def date_dmy(text: str | None) -> date | None:
    """Day-first reading, the convention printed on these receipts."""
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.strip().replace(",", " ")).strip()  # "21 MARCH, 2018" -> "21 MARCH 2018"
    m = re.search(r"\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}[ /\-]?[A-Za-z]{3,9}[ /\-]?\d{2,4}"
                  r"|[A-Za-z]{3,9} \d{1,2} \d{4}|\b\d{8}\b", t)
    cand = m.group() if m else t
    for f in _DMY:
        try:
            return datetime.strptime(cand.title() if "%b" in f or "%B" in f else cand, f).date()
        except ValueError:
            continue
    return None


def money(text: str | None) -> Decimal | None:
    if not text:
        return None
    try:
        return abs(parse_amount(text))
    except (MoneyParseError, InvalidOperation):
        return None


def name_key(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", (text or "").upper())).strip()


def token_f1(a: str, b: str) -> float:
    ta, tb = name_key(a).split(), name_key(b).split()
    if not ta or not tb:
        return 0.0
    common = sum(min(ta.count(t), tb.count(t)) for t in set(ta))
    if not common:
        return 0.0
    p, r = common / len(ta), common / len(tb)
    return 2 * p * r / (p + r)


def pipeline_date(text: str | None, order: str | None) -> date | str | None:
    """What the pipeline's own parser makes of the value: a date, "ambiguous", or None."""
    try:
        return parse_date(text, order) if text else None
    except AmbiguousDateError:
        return "ambiguous"
    except DateParseError:
        return None


# ---------------------------------------------------------------- data


def load_sroie(root: Path, limit: int | None) -> list[dict]:
    docs = []
    for key in sorted((root / "key").glob("*.json")):
        box = next((root / "box" / f"{key.stem}{ext}" for ext in (".csv", ".txt")
                    if (root / "box" / f"{key.stem}{ext}").exists()), None)
        if box is None:
            continue
        lines = [ln.split(",", 8)[8].strip() for ln in box.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.count(",") >= 8]
        docs.append({"id": f"sroie_{key.stem}", "text": "\n".join(lines),
                     "gold": json.loads(key.read_text(encoding="utf-8", errors="replace"))})
    return docs[:limit] if limit else docs


def score(pred: dict, gold: dict, text: str, order: str | None = None) -> dict:
    v, d, t = pred.get("vendor"), pred.get("date"), pred.get("total")
    gd = date_dmy(gold.get("date"))
    gt = money(gold.get("total"))
    pd, nd = date_dmy(d), pipeline_date(d, order)
    same_text = bool(d) and re.sub(r"\s", "", d.upper()) == re.sub(r"\s", "", (gold.get("date") or "").upper())
    out = {
        "vendor": {"read": name_key(v) == name_key(gold.get("company")) and bool(v),
                   "read_lenient": token_f1(v or "", gold.get("company") or "") >= 0.8,
                   "labeled": bool(gold.get("company"))},
        "date": {"read": (gd is not None and pd == gd) or same_text,
                 "normalized": gd is not None and isinstance(nd, date) and nd == gd,
                 "flagged": nd == "ambiguous",
                 "silently_wrong": isinstance(nd, date) and gd is not None and nd != gd,
                 "labeled": bool(gold.get("date"))},
        "total": {"read": gt is not None and money(t) == gt,
                  "normalized": gt is not None and money(t) == gt,
                  "labeled": gt is not None},
    }
    quotes = [q for q in pred.get("quotes", []) if q]
    out["grounded"] = sum(1 for q in quotes if find_span(text, q)) if quotes else 0
    out["quotes"] = len(quotes)
    return out


def extract(llm, doc: dict) -> dict:
    parsed, log = call_schema(llm, PROMPT, doc["text"], InvoiceHeaderExtraction, doc["id"])
    pred = {"error": log.error, "input_tokens": log.input_tokens, "output_tokens": log.output_tokens}
    if parsed is not None:
        pred.update(vendor=parsed.vendor_name.value, date=parsed.issue_date.value, total=parsed.total.value,
                    quotes=[f.source_quote for f in (parsed.vendor_name, parsed.issue_date, parsed.total) if f.value])
    return pred


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    s = {"documents": n, "failed_calls": sum(1 for r in rows if r["pred"].get("error"))}
    for f, kinds in (("vendor", ("read", "read_lenient")), ("date", ("read", "normalized", "flagged", "silently_wrong")),
                     ("total", ("read", "normalized"))):
        lab = [r for r in rows if r["score"][f]["labeled"]]  # receipts whose label for this field is empty are skipped
        for k in kinds:
            c = sum(1 for r in lab if r["score"][f][k])
            s[f"{f}_{k}"] = {"correct": c, "of": len(lab), "accuracy": round(c / len(lab), 3) if lab else None}
    q = sum(r["score"]["quotes"] for r in rows)
    s["quotes_found_verbatim"] = {"found": sum(r["score"]["grounded"] for r in rows), "quotes": q}
    s["input_tokens"] = sum(r["pred"].get("input_tokens", 0) for r in rows)
    s["output_tokens"] = sum(r["pred"].get("output_tokens", 0) for r in rows)
    return s


# ---------------------------------------------------------------- synthetic side


def synthetic_scores(bundle: Path) -> dict:
    """The same three fields from the café extraction (extracted.sqlite) against the printed values."""
    import sqlite3

    conn = sqlite3.connect(str(bundle / "extracted.sqlite"))
    got = {r[0]: r[1:] for r in conn.execute("select invoice_number, printed_vendor_name, issue_date, total from bills")}
    rows = []
    for mf in sorted((bundle / "invoices").glob("*.fields.json")):
        fields = json.loads(mf.read_text())["fields"]
        num = fields["invoice_number"]["text"]
        g = got.get(num)
        rows.append({
            "vendor": bool(g) and name_key(g[0]) == name_key(fields["vendor_name"]["text"]),
            "date": bool(g) and g[1] == parse_date(fields["issue_date"]["text"], "MDY").isoformat(),
            "total": bool(g) and money(str(g[2])) == money(fields["total"]["text"]),
        })
    n = len(rows)
    return {"documents": n, **{f: {"correct": sum(r[f] for r in rows), "accuracy": round(sum(r[f] for r in rows) / n, 3)}
                               for f in FIELDS}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sroie", type=Path, help="folder with box/ and key/ (the mirror's data/ folder)")
    ap.add_argument("--synthetic", type=Path, help="café bundle, for the side-by-side table")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--llm", choices=["claude", "oracle"], default="claude")
    ap.add_argument("--model")
    ap.add_argument("--date-order", choices=["none", "MDY", "DMY"], default="none",
                    help="order the pipeline is told these receipts use (none = unknown: ambiguous dates are flagged)")
    ap.add_argument("--rescore", type=Path, help="re-score a saved data/real/runs/*.jsonl instead of calling the model")
    a = ap.parse_args()

    pipeline.VERBOSE = False  # this script prints its own progress
    docs = load_sroie(a.sroie, a.limit)
    if not docs:
        print(f"no receipts found under {a.sroie} (expected box/ and key/)")
        return 1
    if a.llm == "oracle":  # perfect answers from the labels: checks the scorer, not the model
        from cashbooks.llm.base import LLMResult

        gold = {d["text"]: d["gold"] for d in docs}

        class Oracle:
            model = "oracle"

            def complete(self, system, messages, json_schema=None):
                g = gold[messages[-1].text.split("DOCUMENT TEXT\n\n", 1)[-1]]
                f = lambda v: {"value": v, "source_quote": v, "page": 1}
                empty = {"value": None, "source_quote": None, "page": None}
                body = {k: empty for k in InvoiceHeaderExtraction.model_fields}
                body.update(vendor_name=f(g["company"]), issue_date=f(g["date"]), total=f(g["total"]))
                return LLMResult(text=json.dumps(body), model="oracle")

        llm = Oracle()
    else:
        from cashbooks.llm.claude import ClaudeLLM

        llm = ClaudeLLM(model=a.model)

    order = None if a.date_order == "none" else a.date_order
    if a.rescore:  # no model calls: apply the current scorer and parser to saved predictions
        texts = {d["id"]: d["text"] for d in docs}
        rows = [json.loads(l) for l in open(a.rescore) if l.strip()]
        for r in rows:
            r["score"] = score(r["pred"], r["gold"], texts.get(r["id"], ""), order)
        llm.model = rows[0]["pred"].get("model", llm.model) if rows else llm.model
        return report(a, rows, llm.model, order)
    print(f"extracting {len(docs)} receipts with {llm.model}, {a.workers} at a time")
    done = 0

    def work(doc):
        nonlocal done
        pred = extract(llm, doc)
        pred["model"] = llm.model
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(docs)}", flush=True)
        return {"id": doc["id"], "pred": pred, "gold": doc["gold"], "score": score(pred, doc["gold"], doc["text"], order)}

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        rows = list(pool.map(work, docs))

    return report(a, rows, llm.model, order)


def report(a, rows: list[dict], model: str, order: str | None) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    private = PROJECT / "data" / "real" / "runs"
    private.mkdir(parents=True, exist_ok=True)
    if not a.rescore:
        with open(private / f"{stamp}-sroie-{model}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    report = {"dataset": "SROIE (ICDAR 2019), transcripts from github.com/zzzDavid/ICDAR-2019-SROIE",
              "model": model, "prompt": PROMPT, "date_order_given": order or "none", "real": summarize(rows),
              "failed_ids": {f: sorted(r["id"] for r in rows if r["score"][f]["labeled"] and not r["score"][f]["read"])
                             for f in FIELDS}}
    if a.synthetic:
        report["synthetic"] = synthetic_scores(a.synthetic)
    out = PROJECT / "evaluation" / "results" / f"{stamp}-realdocs-sroie-{model}-order-{order or 'none'}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    r = report["real"]
    pct = lambda x: f"{x['correct']}/{x['of']} ({x['accuracy']:.0%})"
    lines = [f"# Extraction on real receipts vs synthetic invoices", "",
             f"Model `{model}`, prompt `{PROMPT}`, {r['documents']} SROIE receipts, {r['failed_calls']} failed calls.", "",
             "| Field | Synthetic café invoices | Real receipts: value read | Real receipts: after normalization |",
             "| --- | --- | --- | --- |"]
    syn = report.get("synthetic")
    sp = (lambda f: f"{syn[f]['correct']}/{syn['documents']} ({syn[f]['accuracy']:.0%})") if syn else (lambda f: "n/a")
    lines.append(f"| Vendor name | {sp('vendor')} | {pct(r['vendor_read'])} exact, {pct(r['vendor_read_lenient'])} lenient | (no normalization) |")
    lines.append(f"| Date | {sp('date')} | {pct(r['date_read'])} | {pct(r['date_normalized'])} |")
    lines.append(f"| Total | {sp('total')} | {pct(r['total_read'])} | {pct(r['total_normalized'])} |")
    lines += ["", f"Date order given to the parser: {order or 'none (unknown)'}. "
              f"Flagged as ambiguous instead of guessed: {pct(r['date_flagged'])}. "
              f"Turned into a wrong but valid date: {pct(r['date_silently_wrong'])}."]
    q = r["quotes_found_verbatim"]
    lines += ["", f"Quotes found verbatim in the receipt text: {q['found']}/{q['quotes']}. "
              f"Tokens: {r['input_tokens']} in, {r['output_tokens']} out."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
