-- Disponibilidad (Horarios tab) bot toggle. Default OFF (ADR-0007).
-- Safe to re-run.
SET NAMES utf8mb4;

SET @has_disp := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'clinic_settings'
    AND COLUMN_NAME = 'disponibilidad_enabled'
);
SET @sql_disp := IF(
  @has_disp = 0,
  'ALTER TABLE clinic_settings ADD COLUMN disponibilidad_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER welcome_text',
  'SELECT 1'
);
PREPARE stmt_d FROM @sql_disp;
EXECUTE stmt_d;
DEALLOCATE PREPARE stmt_d;

UPDATE clinic_settings
SET disponibilidad_enabled = 0
WHERE id = 1;
