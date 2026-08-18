-- Replace Alejandro Artigas with Maria Eugenia Sibay (idempotent).
-- Availability rows for Alejandro are removed via ON DELETE CASCADE.
SET NAMES utf8mb4;

DELETE FROM doctors WHERE name = 'Alejandro Artigas';

INSERT INTO doctors (name, active, sort_order)
SELECT 'Maria Eugenia Sibay', 1, 3
WHERE NOT EXISTS (
  SELECT 1 FROM doctors WHERE name = 'Maria Eugenia Sibay'
);
