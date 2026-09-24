"""Weekly solicitud KPIs for the dashboard (Mon–Sun, by created_at)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from confirmacion import CONFIRMED_STATUS, normalize_tipo

MONTHS_ES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_bounds(today: date | None = None) -> tuple[date, date, date, date]:
    """Return (current_start, current_end, previous_start, previous_end) inclusive."""
    today = today or date.today()
    current_start = monday_of(today)
    current_end = current_start + timedelta(days=6)
    previous_start = current_start - timedelta(days=7)
    previous_end = current_start - timedelta(days=1)
    return current_start, current_end, previous_start, previous_end


def week_label(start: date, end: date) -> str:
    """e.g. 'Semana del 21 al 27 de septiembre, 2026'."""
    if start.month == end.month and start.year == end.year:
        return (
            f"Semana del {start.day} al {end.day} de {MONTHS_ES[start.month]}, "
            f"{start.year}"
        )
    if start.year == end.year:
        return (
            f"Semana del {start.day} de {MONTHS_ES[start.month]} al "
            f"{end.day} de {MONTHS_ES[end.month]}, {start.year}"
        )
    return (
        f"Semana del {start.day} de {MONTHS_ES[start.month]} {start.year} al "
        f"{end.day} de {MONTHS_ES[end.month]} {end.year}"
    )


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "").replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def classify_row(row: dict[str, Any]) -> str | None:
    """Return bucket: confirmados | reprogramaciones | cancelaciones | None.

    Reprogramaciones / cancelaciones count incoming solicitudes by tipo
    (reprogramar / cancelar), regardless of status. Confirmados are panel
    confirmations (status=confirmed) that are not those tipos.
    """
    tipo = normalize_tipo(row.get("tipo"))
    if tipo == "reprogramar":
        return "reprogramaciones"
    if tipo == "cancelar":
        return "cancelaciones"
    status = str(row.get("status") or "").strip().lower()
    if status == CONFIRMED_STATUS:
        return "confirmados"
    return None


def empty_counts() -> dict[str, int]:
    return {
        "total": 0,
        "confirmados": 0,
        "reprogramaciones": 0,
        "cancelaciones": 0,
    }


def count_rows_in_week(
    rows: list[dict[str, Any]], week_start: date, week_end: date
) -> dict[str, int]:
    counts = empty_counts()
    for row in rows:
        created = _as_date(row.get("created_at"))
        if created is None or created < week_start or created > week_end:
            continue
        counts["total"] += 1
        bucket = classify_row(row)
        if bucket:
            counts[bucket] += 1
    return counts


def pct_change_trend(current: int, previous: int) -> dict[str, Any]:
    """WoW % when prior > 0; else absolute delta label."""
    delta = current - previous
    if previous > 0:
        pct = round((delta / previous) * 100)
        sign = "+" if pct > 0 else ""
        return {
            "pct": pct,
            "delta": delta,
            "label": f"{sign}{pct}% vs semana anterior",
        }
    if delta > 0:
        return {"pct": None, "delta": delta, "label": f"+{delta} vs semana anterior"}
    if delta < 0:
        return {"pct": None, "delta": delta, "label": f"{delta} vs semana anterior"}
    return {"pct": None, "delta": 0, "label": "sin cambio vs semana anterior"}


def cancelaciones_share_trend(cancelaciones: int, total: int) -> dict[str, Any]:
    if total <= 0:
        pct = 0
    else:
        pct = round((cancelaciones / total) * 100)
    return {"pct": pct, "delta": None, "label": f"{pct}% del total"}


def build_trends(current: dict[str, int], previous: dict[str, int]) -> dict[str, Any]:
    return {
        "total": pct_change_trend(current["total"], previous["total"]),
        "confirmados": pct_change_trend(
            current["confirmados"], previous["confirmados"]
        ),
        "reprogramaciones": pct_change_trend(
            current["reprogramaciones"], previous["reprogramaciones"]
        ),
        "cancelaciones": cancelaciones_share_trend(
            current["cancelaciones"], current["total"]
        ),
    }


def compute_solicitudes_week_stats(
    rows: list[dict[str, Any]], *, today: date | None = None
) -> dict[str, Any]:
    """Aggregate KPIs from solicitud rows (created_at + status/tipo)."""
    current_start, current_end, previous_start, previous_end = week_bounds(today)
    current = count_rows_in_week(rows, current_start, current_end)
    previous = count_rows_in_week(rows, previous_start, previous_end)
    return {
        "week_start": current_start.isoformat(),
        "week_end": current_end.isoformat(),
        "week_label": week_label(current_start, current_end),
        "current": current,
        "previous": previous,
        "trends": build_trends(current, previous),
    }
