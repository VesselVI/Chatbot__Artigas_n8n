"""Outbound WhatsApp copy for Confirmación desde el panel."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from confirmacion import normalize_tipo


def format_dia_hora_display(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value or "").strip().replace("T", " ")[:16]
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        except ValueError:
            return str(value or "")
    return dt.strftime("%d/%m/%Y %H:%M")


def build_mensaje_confirmacion(
    *,
    nombre: str,
    medico: str,
    appointment_at: Any,
    nota_paciente: str = "",
    include_nota: bool = True,
) -> str:
    lines = [
        "✅ TURNO CONFIRMADO",
        "",
        f"Nombre: {nombre}",
        f"Médico: {medico}",
        f"Día y hora: {format_dia_hora_display(appointment_at)}",
    ]
    nota = (nota_paciente or "").strip()
    if include_nota and nota:
        lines.append(f"Nota: {nota}")
    lines.extend(
        [
            "",
            "Te esperamos unos minutos antes del horario. Si necesitás reprogramar o cancelar, escribinos por acá. Escribí menú para volver.",
        ]
    )
    return "\n".join(lines)


def build_mensaje_reprogramacion(
    *,
    nombre: str,
    medico: str,
    appointment_at: Any,
    nota_paciente: str = "",
    include_nota: bool = True,
) -> str:
    lines = [
        "✅ TURNO REPROGRAMADO",
        "",
        f"Nombre: {nombre}",
        f"Médico: {medico}",
        f"Nuevo día y hora: {format_dia_hora_display(appointment_at)}",
    ]
    nota = (nota_paciente or "").strip()
    if include_nota and nota:
        lines.append(f"Nota: {nota}")
    lines.extend(
        [
            "",
            "Su turno anterior fue cancelado. Agende este nuevo horario. Escribí menú para volver.",
        ]
    )
    return "\n".join(lines)


def build_outbound_message(
    tipo: Any,
    *,
    nombre: str,
    medico: str,
    appointment_at: Any,
    nota_paciente: str = "",
    include_nota: bool = True,
) -> str:
    if normalize_tipo(tipo) == "reprogramar":
        return build_mensaje_reprogramacion(
            nombre=nombre,
            medico=medico,
            appointment_at=appointment_at,
            nota_paciente=nota_paciente,
            include_nota=include_nota,
        )
    return build_mensaje_confirmacion(
        nombre=nombre,
        medico=medico,
        appointment_at=appointment_at,
        nota_paciente=nota_paciente,
        include_nota=include_nota,
    )
