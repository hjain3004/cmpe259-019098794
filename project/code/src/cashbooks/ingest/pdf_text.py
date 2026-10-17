"""Read text from text-native PDFs, one string per page.

Page strings are kept exactly as pdfplumber returns them so that character
offsets into them stay valid. Use `collapse_ws` only for matching.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

_WS = re.compile(r"\s+")


def page_texts(pdf_path: str | Path) -> list[str]:
    """Return the extracted text of every page, in order. Empty pages give ""."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def collapse_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def find_span(page: str, quote: str) -> tuple[int, int, str] | None:
    """Locate `quote` in `page`, tolerating whitespace differences.

    Returns (start, end, exact_text_on_page) or None if the quote is not there.
    """
    if not quote.strip():
        return None
    i = page.find(quote)
    if i >= 0:
        return i, i + len(quote), quote
    parts = [re.escape(p) for p in quote.split()]
    m = re.search(r"\s+".join(parts), page)
    if m:
        return m.start(), m.end(), m.group()
    return None
