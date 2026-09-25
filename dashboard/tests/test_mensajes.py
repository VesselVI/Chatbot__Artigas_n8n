"""Message body builders for Confirmación desde el panel."""

from datetime import datetime

from mensajes import build_mensaje_confirmacion, build_mensaje_reprogramacion, build_outbound_message


def test_mensaje_confirmacion_omits_empty_nota():
    text = build_mensaje_confirmacion(
        nombre="Ana",
        medico="Adrian Artigas",
        appointment_at=datetime(2026, 9, 22, 10, 30),
        nota_paciente="",
    )
    assert "✅ TURNO CONFIRMADO" in text
    assert "Nombre: Ana" in text
    assert "Día y hora: 22/09/2026 10:30" in text
    assert "Nota:" not in text
    assert "Te esperamos" in text


def test_mensaje_confirmacion_includes_nota():
    text = build_mensaje_confirmacion(
        nombre="Ana",
        medico="Adrian Artigas",
        appointment_at="2026-09-22T10:30",
        nota_paciente="Traiga estudios",
    )
    assert "Nota: Traiga estudios" in text


def test_mensaje_reprogramacion_copy():
    text = build_mensaje_reprogramacion(
        nombre="Ana",
        medico="Adrian Artigas",
        appointment_at=datetime(2026, 9, 23, 16, 0),
        nota_paciente="",
    )
    assert text.startswith("TURNO REPROGRAMADO")
    assert "Nuevo día y hora: 23/09/2026 16:00" in text
    assert "Su turno ha sido reprogramado" in text
    assert "Escribí menú para volver" in text
    assert "Por orden de llegada" not in text


def test_outbound_picks_by_tipo():
    t = build_outbound_message(
        "reprogramar",
        nombre="A",
        medico="B",
        appointment_at=datetime(2026, 9, 22, 10, 0),
    )
    assert "TURNO REPROGRAMADO" in t


def test_mensaje_confirmacion_por_orden_de_llegada():
    text = build_mensaje_confirmacion(
        nombre="Ana",
        medico="Adrian Artigas",
        appointment_at=datetime(2026, 9, 23, 0, 0),
        por_orden_de_llegada=True,
    )
    assert text.startswith("👤 INFORMACION DEL TURNO")
    assert "✅ TURNO CONFIRMADO" not in text
    assert "Día: 23/09/2026 — Por orden de llegada" in text
    assert "Día y hora:" not in text
    assert "por orden de llegada" in text.lower()
