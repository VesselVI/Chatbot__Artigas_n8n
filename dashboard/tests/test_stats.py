"""Unit tests for weekly solicitud KPI aggregation."""

from datetime import date, datetime

from stats import (
    classify_row,
    compute_solicitudes_week_stats,
    count_rows_in_week,
    pct_change_trend,
    week_bounds,
    week_label,
)


def test_week_bounds_monday_sunday():
    # Wednesday 2026-09-23 → week Mon 21 – Sun 27; prev Mon 14 – Sun 20
    cur_s, cur_e, prev_s, prev_e = week_bounds(date(2026, 9, 23))
    assert cur_s == date(2026, 9, 21)
    assert cur_e == date(2026, 9, 27)
    assert prev_s == date(2026, 9, 14)
    assert prev_e == date(2026, 9, 20)


def test_week_label_same_month():
    assert (
        week_label(date(2026, 9, 21), date(2026, 9, 27))
        == "Semana del 21 al 27 de septiembre, 2026"
    )


def test_classify_row_buckets():
    assert classify_row({"status": "confirmed", "tipo": "turno"}) == "confirmados"
    assert classify_row({"status": "confirmed", "tipo": "reprogramar"}) == "reprogramados"
    assert classify_row({"status": "cancelled", "tipo": "turno"}) == "cancelados"
    assert classify_row({"status": "pending", "tipo": "turno"}) is None


def test_pct_change_trend():
    assert pct_change_trend(28, 25)["label"] == "+12% vs semana anterior"
    assert pct_change_trend(20, 25)["label"] == "-20% vs semana anterior"
    assert pct_change_trend(5, 0)["label"] == "+5 vs semana anterior"
    assert pct_change_trend(0, 0)["label"] == "sin cambio vs semana anterior"


def _row(created, status="pending", tipo="turno"):
    return {"created_at": created, "status": status, "tipo": tipo}


def test_compute_solicitudes_week_stats_counts_and_trends():
    today = date(2026, 9, 23)
    rows = [
        # current week
        _row(datetime(2026, 9, 22, 10, 0), "pending", "turno"),
        _row(datetime(2026, 9, 22, 11, 0), "confirmed", "turno"),
        _row(datetime(2026, 9, 23, 9, 0), "confirmed", "reprogramar"),
        _row(datetime(2026, 9, 24, 9, 0), "cancelled", "cancelar"),
        _row(datetime(2026, 9, 21, 8, 0), "confirmed", "estudio"),
        # previous week
        _row(datetime(2026, 9, 15, 10, 0), "confirmed", "turno"),
        _row(datetime(2026, 9, 16, 10, 0), "confirmed", "turno"),
        _row(datetime(2026, 9, 17, 10, 0), "cancelled", "cancelar"),
        # outside range
        _row(datetime(2026, 9, 1, 10, 0), "confirmed", "turno"),
    ]
    out = compute_solicitudes_week_stats(rows, today=today)
    assert out["week_start"] == "2026-09-21"
    assert out["week_end"] == "2026-09-27"
    assert out["current"] == {
        "total": 5,
        "confirmados": 2,
        "reprogramados": 1,
        "cancelados": 1,
    }
    assert out["previous"] == {
        "total": 3,
        "confirmados": 2,
        "reprogramados": 0,
        "cancelados": 1,
    }
    # total 5 vs 3 → +67%
    assert out["trends"]["total"]["pct"] == 67
    assert "+67%" in out["trends"]["total"]["label"]
    # cancelados share of current total: 1/5 → 20%
    assert out["trends"]["cancelados"]["label"] == "20% del total"
    assert "septiembre" in out["week_label"]


def test_count_rows_string_created_at():
    start = date(2026, 9, 21)
    end = date(2026, 9, 27)
    rows = [
        _row("2026-09-22 10:00:00", "confirmed", "turno"),
        _row("2026-09-20", "confirmed", "turno"),  # previous week
    ]
    counts = count_rows_in_week(rows, start, end)
    assert counts["total"] == 1
    assert counts["confirmados"] == 1
