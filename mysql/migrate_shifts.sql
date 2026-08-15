-- Add mañana/noche shifts to doctor_availability (idempotent for existing VPS).
SET NAMES utf8mb4;

-- New installs already have `shift`. Skip if the column exists.
SET @has_shift := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'doctor_availability'
    AND COLUMN_NAME = 'shift'
);

SET @sql := IF(
  @has_shift = 0,
  'ALTER TABLE doctor_availability ADD COLUMN shift ENUM(''manana'',''noche'') NOT NULL DEFAULT ''manana'' AFTER day',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_pk_shift := (
  SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'doctor_availability'
    AND CONSTRAINT_NAME = 'PRIMARY'
    AND COLUMN_NAME = 'shift'
);

SET @sql := IF(
  @has_pk_shift = 0,
  'ALTER TABLE doctor_availability DROP PRIMARY KEY, ADD PRIMARY KEY (doctor_id, week_start, day, shift)',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE doctor_availability
SET shift = IF(start_time IS NOT NULL AND start_time < '14:00:00', 'manana', 'noche')
WHERE is_unavailable = 0;

UPDATE doctor_availability
SET shift = 'manana'
WHERE is_unavailable = 1;
