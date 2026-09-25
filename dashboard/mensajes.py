"""Outbound WhatsApp copy for Confirmación desde el panel."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from confirmacion import normalize_tipo


def format_dia_hora_display(
    value: Any, *, por_orden_de_llegada: bool = False
) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value or "").strip().replace("T", " ")[:16]
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                dt = datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return str(value or "")
    if por_orden_de_llegada:
        return f"{dt.strftime('%d/%m/%Y')} — Por orden de llegada"
    return dt.strftime("%d/%m/%Y %H:%M")


def build_mensaje_confirmacion(
    *,
    nombre: str,
    medico: str,
    appointment_at: Any,
    nota_paciente: str = "",
    include_nota: bool = True,
    por_orden_de_llegada: bool = False,
) -> str:
    if por_orden_de_llegada:
        title = "👤 INFORMACION DEL TURNO"
        dia_line = f"Día: {format_dia_hora_display(appointment_at, por_orden_de_llegada=True)}"
        footer = (
            "Presentate el día indicado; te atenderán por orden de llegada. "
            "Si necesitás reprogramar o cancelar, escribinos por acá. Escribí menú para volver."
        )
    else:
        title = "✅ TURNO CONFIRMADO"
        dia_line = f"Día y hora: {format_dia_hora_display(appointment_at)}"
        footer = (
            "Te esperamos unos minutos antes del horario. "
            "Si necesitás reprogramar o cancelar, escribinos por acá. Escribí menú para volver."
        )
    lines = [
        title,
        "",
        f"Nombre: {nombre}",
        f"Médico: {medico}",
        dia_line,
    ]
    nota = (nota_paciente or "").strip()
    if include_nota and nota:
        lines.append(f"Nota: {nota}")
    lines.extend(["", footer])
    return "\n".join(lines)


def build_mensaje_reprogramacion(
    *,
    nombre: str,
    medico: str,
    appointment_at: Any,
    nota_paciente: str = "",
    include_nota: bool = True,
    por_orden_de_llegada: bool = False,
) -> str:
    # Match Meta plantilla confirmacion_reprogramacion (es_AR) — always día+hora.
    _ = por_orden_de_llegada
    lines = [
        "TURNO REPROGRAMADO",
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
            "Su turno ha sido reprogramado. Agende este nuevo horario. "
            "Escribí menú para volver.",
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
    por_orden_de_llegada: bool = False,
) -> str:
    if normalize_tipo(tipo) == "reprogramar":
        return build_mensaje_reprogramacion(
            nombre=nombre,
            medico=medico,
            appointment_at=appointment_at,
            nota_paciente=nota_paciente,
            include_nota=include_nota,
            por_orden_de_llegada=por_orden_de_llegada,
        )
    return build_mensaje_confirmacion(
        nombre=nombre,
        medico=medico,
        appointment_at=appointment_at,
        nota_paciente=nota_paciente,
        include_nota=include_nota,
        por_orden_de_llegada=por_orden_de_llegada,
    )
