"""
Idempotent: add Día/hora del turno + Nota al paciente + WhatsApp send outcome
for Confirmación desde el panel. Safe to re-run on live VPS.
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

SET @has_send_status := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'whatsapp_send_status'
);
SET @sql_send_status := IF(
  @has_send_status = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN whatsapp_send_status VARCHAR(20) NULL DEFAULT NULL AFTER nota_paciente',
  'SELECT 1'
);
PREPARE stmt_s FROM @sql_send_status;
EXECUTE stmt_s;
DEALLOCATE PREPARE stmt_s;

SET @has_send_channel := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'whatsapp_send_channel'
);
SET @sql_send_channel := IF(
  @has_send_channel = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN whatsapp_send_channel VARCHAR(20) NULL DEFAULT NULL AFTER whatsapp_send_status',
  'SELECT 1'
);
PREPARE stmt_c FROM @sql_send_channel;
EXECUTE stmt_c;
DEALLOCATE PREPARE stmt_c;

SET @has_nota_omitted := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'whatsapp_nota_omitted'
);
SET @sql_nota_omitted := IF(
  @has_nota_omitted = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN whatsapp_nota_omitted TINYINT(1) NOT NULL DEFAULT 0 AFTER whatsapp_send_channel',
  'SELECT 1'
);
PREPARE stmt_o FROM @sql_nota_omitted;
EXECUTE stmt_o;
DEALLOCATE PREPARE stmt_o;
