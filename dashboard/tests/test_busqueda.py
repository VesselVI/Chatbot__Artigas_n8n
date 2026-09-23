"""Unit tests for patient search / autocomplete domain (#10)."""

from busqueda import filter_solicitudes_by_query, fold_text, solicitud_matches_query


def test_fold_strips_accents():
    assert fold_text("María Gómez") == "maria gomez"


def test_match_by_nombre_substring():
    row = {"nombre": "Ana Pérez", "phone": "5491112345678", "telefono_contacto": ""}
    assert solicitud_matches_query(row, "ana") is True
    assert solicitud_matches_query(row, "pez") is False
    assert solicitud_matches_query(row, "pérez") is True


def test_match_by_phone_digits():
    row = {"nombre": "X", "phone": "54911-1234-5678", "telefono_contacto": ""}
    assert solicitud_matches_query(row, "111234") is True
    assert solicitud_matches_query(row, "99") is False  # short / no match
    assert solicitud_matches_query(row, "000") is False


def test_match_by_telefono_contacto():
    row = {
        "nombre": "Luis",
        "phone": "5491100000000",
        "telefono_contacto": "5491199988877",
    }
    assert solicitud_matches_query(row, "999888") is True


def test_empty_query_matches_nothing():
    row = {"nombre": "Ana", "phone": "54911", "telefono_contacto": ""}
    assert solicitud_matches_query(row, "") is False
    assert filter_solicitudes_by_query([row], "  ") == []


def test_filter_preserves_order_and_limit():
    rows = [
        {"id": 1, "nombre": "Ana Uno", "phone": "1", "telefono_contacto": ""},
        {"id": 2, "nombre": "Ana Dos", "phone": "2", "telefono_contacto": ""},
        {"id": 3, "nombre": "Ana Tres", "phone": "3", "telefono_contacto": ""},
        {"id": 4, "nombre": "Bruno", "phone": "4", "telefono_contacto": ""},
    ]
    out = filter_solicitudes_by_query(rows, "ana", limit=2)
    assert [r["id"] for r in out] == [1, 2]
