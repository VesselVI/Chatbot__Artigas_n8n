-- Add `solicitud` to turno_solicitudes.tipo (secretary-only handoffs).
-- Idempotent: safe if already present. Run on VPS after pull.
SET NAMES utf8mb4;

SET @has_solicitud := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'tipo'
    AND COLUMN_TYPE LIKE '%solicitud%'
);

SET @sql := IF(
  @has_solicitud = 0,
  'ALTER TABLE turno_solicitudes MODIFY COLUMN tipo ENUM(''turno'',''cancelar'',''estudio'',''reprogramar'',''solicitud'') NOT NULL DEFAULT ''turno''',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
