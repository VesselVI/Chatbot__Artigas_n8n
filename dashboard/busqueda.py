"""Domain search helpers for patient autocomplete (#10)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def fold_text(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def digits_only(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def solicitud_matches_query(row: dict[str, Any], query: str) -> bool:
    """True if nombre or phone fields contain the query (name fold or digit substring)."""
    q = str(query or "").strip()
    if not q:
        return False
    q_fold = fold_text(q)
    q_digits = digits_only(q)
    nombre = fold_text(row.get("nombre"))
    phone_fold = fold_text(row.get("phone"))
    contacto_fold = fold_text(row.get("telefono_contacto"))
    phone_digits = digits_only(
        f"{row.get('phone') or ''}{row.get('telefono_contacto') or ''}"
    )
    if q_fold and q_fold in nombre:
        return True
    if q_fold and (q_fold in phone_fold or q_fold in contacto_fold):
        return True
    if len(q_digits) >= 3 and q_digits in phone_digits:
        return True
    return False


def filter_solicitudes_by_query(
    rows: list[dict[str, Any]],
    query: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return up to `limit` matching rows (stable input order preserved)."""
    q = str(query or "").strip()
    if not q or limit <= 0:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if solicitud_matches_query(row, q):
            out.append(row)
            if len(out) >= limit:
                break
    return out
