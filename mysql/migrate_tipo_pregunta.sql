-- Retire tipo=solicitud → pregunta (ADR-0007). Safe-ish re-run patterns below.

-- 1) Widen ENUM to include pregunta (keep solicitud temporarily for rewrite).
ALTER TABLE turno_solicitudes
  MODIFY COLUMN tipo ENUM(
    'turno',
    'cancelar',
    'estudio',
    'reprogramar',
    'solicitud',
    'pregunta'
  ) NOT NULL DEFAULT 'turno';

UPDATE turno_solicitudes
SET tipo = 'pregunta'
WHERE tipo = 'solicitud';

-- 2) Drop solicitud from ENUM after data rewrite.
ALTER TABLE turno_solicitudes
  MODIFY COLUMN tipo ENUM(
    'turno',
    'cancelar',
    'estudio',
    'reprogramar',
    'pregunta'
  ) NOT NULL DEFAULT 'turno';
