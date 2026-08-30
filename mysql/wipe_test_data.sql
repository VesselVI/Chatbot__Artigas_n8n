-- Wipe bot test data before clinic WhatsApp go-live.
-- Keeps doctors, weekly hours (doctor_availability), and clinic_settings.
-- Run ONLY after a MySQL dump (scripts/backup-mysql.sh).
SET NAMES utf8mb4;

TRUNCATE TABLE turno_solicitudes;
TRUNCATE TABLE conversation_state;
