-- Preguntas frecuentes (curated Q&A for the bot). ADR-0007 / Feature 3.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS preguntas_frecuentes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  pregunta VARCHAR(500) NOT NULL,
  respuesta TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
