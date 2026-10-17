# cmpe259-019098794

Coursework for CMPE 259 Natural Language Processing, San José State University, Fall 2026 (Himanshu Jain).

## Directory guide

| Folder | Contents |
|---|---|
| [`homework/`](homework/) | Homework assignments, one folder each (`hw1/` … `hw5/`) |
| [`class-activities/`](class-activities/) | In-class activities (`ca1/` … `ca4/`) |
| [`project/`](project/) | Term project: **CashBooks Assist**, a read-only LLM assistant for vendor-bill and payment reconciliation. See [`project/README.md`](project/README.md). |
| [`misc/`](misc/) | Anything that doesn't fit above |

### Project at a glance

| Folder | Contents |
|---|---|
| [`project/proposal/`](project/proposal/) | Submitted proposal |
| [`project/checkins/`](project/checkins/) | Check-in reports |
| [`project/docs/`](project/docs/) | Design plan, decision log, references |
| [`project/code/`](project/code/) | Python package, tests, JSON Schemas |
| [`project/data/`](project/data/) | Synthetic scenario generator and bundles |
| [`project/prompts/`](project/prompts/) | Prompt templates |
| [`project/evaluation/`](project/evaluation/) | Test conversations, runners, results |
| [`project/demo/`](project/demo/) | Demo recording and script |

## Setup

Requires Python 3.11 or newer.

```
python -m venv .venv
source .venv/bin/activate
pip install -e "project/code[dev]"
cd project/code && pytest
```

Project usage, data and credentials are described in [`project/README.md`](project/README.md). No credentials are stored in this repository.
