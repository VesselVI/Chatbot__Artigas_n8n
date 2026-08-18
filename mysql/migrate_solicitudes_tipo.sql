-- Add tipo labels on turno_solicitudes (idempotent for existing VPS).
-- New installs already have `tipo` from init.sql. Skip if the column exists.
SET NAMES utf8mb4;

SET @has_tipo := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'turno_solicitudes'
    AND COLUMN_NAME = 'tipo'
);

SET @sql := IF(
  @has_tipo = 0,
  'ALTER TABLE turno_solicitudes ADD COLUMN tipo ENUM(''turno'',''cancelar'',''estudio'') NOT NULL DEFAULT ''turno'' AFTER conversation_id',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Existing rows stay `turno` via DEFAULT.
