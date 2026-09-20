"""
Idempotent: add Día/hora del turno + Nota al paciente for Confirmación desde el panel.
Safe to re-run on live VPS. init.sql is only applied on first MySQL volume.
"""
SET NAMES utf8mb4;

SET @has_appointment := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'appointment_at'
);
SET @sql_appointment := IF(
  @has_appointment = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN appointment_at DATETIME NULL DEFAULT NULL AFTER horario_preferido',
  'SELECT 1'
);
PREPARE stmt_a FROM @sql_appointment;
EXECUTE stmt_a;
DEALLOCATE PREPARE stmt_a;

SET @has_nota := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'nota_paciente'
);
SET @sql_nota := IF(
  @has_nota = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN nota_paciente TEXT NULL AFTER appointment_at',
  'SELECT 1'
);
PREPARE stmt_n FROM @sql_nota;
EXECUTE stmt_n;
DEALLOCATE PREPARE stmt_n;
