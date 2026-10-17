"""Write every contract's JSON Schema to schemas/ so prompts and reviewers see the same shapes.

    python -m cashbooks.contracts.export
"""

import json
from pathlib import Path

from .evaluation import LogRow, QuerySuite
from .extraction import InvoiceHeaderExtraction, LineItemsExtraction, MessageClaimExtraction
from .response import AssistantResponse
from .tools import tool_definitions

OUT = Path(__file__).resolve().parents[3] / "schemas"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    models = {
        "extraction_invoice_header": InvoiceHeaderExtraction,
        "extraction_line_items": LineItemsExtraction,
        "extraction_message_claim": MessageClaimExtraction,
        "response": AssistantResponse,
        "query_suite": QuerySuite,
        "log_row": LogRow,
    }
    for name, model in models.items():
        (OUT / f"{name}.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
    (OUT / "tools.json").write_text(json.dumps(tool_definitions(), indent=2) + "\n")
    print(f"wrote {len(models) + 1} schemas to {OUT}")


if __name__ == "__main__":
    main()
