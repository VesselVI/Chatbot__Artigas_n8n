-- Idempotent: flag for Confirmación «por orden de llegada» (day only, no clock time).
-- Safe to re-run on live VPS.
SET NAMES utf8mb4;

SET @has_orden := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'por_orden_de_llegada'
);
SET @sql_orden := IF(
  @has_orden = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN por_orden_de_llegada TINYINT(1) NOT NULL DEFAULT 0 AFTER appointment_at',
  'SELECT 1'
);
PREPARE stmt_o FROM @sql_orden;
EXECUTE stmt_o;
DEALLOCATE PREPARE stmt_o;
