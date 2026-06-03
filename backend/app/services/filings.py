"""Filings explorer service (PRD 18)."""
from __future__ import annotations

import re

import httpx

from ..core.config import settings
from ..core.errors import ValidationError
from ..core.http import get_text
from ..providers.registry import run_chain

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)

# 8-K item code labels (subset).
ITEM_LABELS = {
    "1.01": "Material agreement", "1.02": "Termination of agreement",
    "2.02": "Results / earnings", "2.03": "Material obligation",
    "3.02": "Unregistered equity sale", "5.02": "Officer/director change",
    "5.07": "Shareholder vote", "7.01": "Regulation FD", "8.01": "Other events",
    "9.01": "Financial statements & exhibits",
}


def filings(ticker: str, *, forms: list[str] | None = None, limit: int = 50) -> dict:
    rows, served_by = run_chain("filings", "get_filings", ticker, forms=forms, limit=limit)
    out = []
    for f in rows:
        d = f.model_dump()
        if d.get("items"):
            codes = [c.strip() for c in str(d["items"]).split(",") if c.strip()]
            d["item_labels"] = [{"code": c, "label": ITEM_LABELS.get(c, "")} for c in codes]
        out.append(d)
    return {"filings": out, "served_by": served_by}


def document(url: str) -> dict:
    """Fetch a filing document for the in-app reader (PRD 18).

    SSRF guard: only sec.gov URLs are allowed. Scripts are stripped and a <base>
    tag injected so relative resources (images/CSS) resolve back to EDGAR.
    """
    host = httpx.URL(url).host or ""
    if not (host == "sec.gov" or host.endswith(".sec.gov")):
        raise ValidationError("Only SEC EDGAR documents can be opened in the reader", url=url)

    raw = get_text(url, headers={"User-Agent": settings.sec_user_agent}, provider="sec_edgar")
    base = url.rsplit("/", 1)[0] + "/"
    cleaned = _SCRIPT_RE.sub("", raw)
    # Strip the XML declaration / PIs so the browser parses iXBRL docs as HTML, not XML.
    cleaned = re.sub(r"<\?xml[^>]*\?>", "", cleaned, flags=re.IGNORECASE).lstrip()

    is_html = "<html" in cleaned[:2000].lower() or "<table" in cleaned[:5000].lower()
    if is_html:
        base_tag = f'<base href="{base}">'
        if re.search(r"<head\b[^>]*>", cleaned, re.IGNORECASE):
            cleaned = re.sub(r"(<head\b[^>]*>)", r"\1" + base_tag, cleaned, count=1, flags=re.IGNORECASE)
        else:
            cleaned = base_tag + cleaned
        body = cleaned
    else:
        # plain-text submission (e.g. older filings) — render as preformatted text
        escaped = cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = f'<base href="{base}"><pre style="white-space:pre-wrap;font-family:monospace">{escaped}</pre>'

    return {"html": body, "url": url}
