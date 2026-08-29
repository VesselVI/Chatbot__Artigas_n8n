-- Align public clinic hours with secretary attention windows (8–12 and 16–20).
-- Safe to re-run on live VPS. init.sql only applies on first MySQL volume.

UPDATE clinic_settings
SET clinic_hours = 'Lunes a Viernes de 8hs a 12hs y de 16hs a 20hs'
WHERE id = 1;
