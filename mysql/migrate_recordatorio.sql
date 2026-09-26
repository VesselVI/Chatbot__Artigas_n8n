-- Idempotent: Recordatorio automatico (~24h) tracking column.
-- Safe to re-run on live VPS.
SET NAMES utf8mb4;

SET @has_reminder := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'reminder_sent_at'
);
SET @sql_reminder := IF(
  @has_reminder = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN reminder_sent_at DATETIME NULL DEFAULT NULL AFTER whatsapp_nota_omitted',
  'SELECT 1'
);
PREPARE stmt_r FROM @sql_reminder;
EXECUTE stmt_r;
DEALLOCATE PREPARE stmt_r;
