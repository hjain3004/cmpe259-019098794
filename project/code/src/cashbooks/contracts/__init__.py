"""Typed contracts between every stage of CashBooks Assist.

extraction  -> what the extraction LLM returns (raw strings + verbatim quotes)
records     -> normalized rows stored in SQLite
tools       -> arguments and results of the seven read-only tools
response    -> the JSON object every configuration (C1-C4) must return
postprocess -> code applied to every response before display or scoring
evaluation  -> the frozen query file and the per-run log row
"""

from .common import Answerability, Money, PaymentState
from .extraction import InvoiceHeaderExtraction, LineItemsExtraction, MessageClaimExtraction
from .postprocess import postprocess
from .response import AssistantResponse, Calculation, Citation
from .tools import TOOLS, parse_tool_call, tool_definitions

__all__ = [
    "Answerability", "Money", "PaymentState",
    "InvoiceHeaderExtraction", "LineItemsExtraction", "MessageClaimExtraction",
    "AssistantResponse", "Calculation", "Citation", "postprocess",
    "TOOLS", "parse_tool_call", "tool_definitions",
]
