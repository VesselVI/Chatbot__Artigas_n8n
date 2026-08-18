-- Clínica Artigas chatbot schema
SET NAMES utf8mb4;
SET time_zone = '-03:00';

CREATE TABLE IF NOT EXISTS conversation_state (
  phone VARCHAR(20) NOT NULL,
  state VARCHAR(50) DEFAULT 'idle',
  context JSON DEFAULT (JSON_OBJECT()),
  updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS doctors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS doctor_availability (
  doctor_id INT NOT NULL,
  week_start DATE NOT NULL,
  day TINYINT NOT NULL COMMENT '0=Mon .. 6=Sun',
  shift ENUM('manana','noche') NOT NULL DEFAULT 'manana',
  is_unavailable TINYINT(1) NOT NULL DEFAULT 0,
  start_time TIME NULL,
  end_time TIME NULL,
  PRIMARY KEY (doctor_id, week_start, day, shift),
  CONSTRAINT fk_avail_doctor FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS clinic_settings (
  id TINYINT NOT NULL PRIMARY KEY DEFAULT 1,
  address VARCHAR(255) NOT NULL DEFAULT 'Avenida Nicolas Avellaneda 347',
  clinic_hours VARCHAR(255) NOT NULL DEFAULT 'Lunes a Viernes de 9hs a 12hs y de 16hs a 19hs',
  obras_sociales JSON NOT NULL,
  welcome_text VARCHAR(500) NOT NULL DEFAULT '¡Hola! Bienvenido/a a la Clínica Oftalmológica Artigas. ¿En qué te puedo ayudar?',
  updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS turno_solicitudes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  phone VARCHAR(20) NOT NULL,
  nombre VARCHAR(120) DEFAULT NULL,
  dni VARCHAR(40) DEFAULT NULL,
  obra_social VARCHAR(120) DEFAULT NULL,
  telefono_contacto VARCHAR(40) DEFAULT NULL,
  medico VARCHAR(120) DEFAULT NULL,
  horario_preferido VARCHAR(255) DEFAULT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  conversation_id VARCHAR(64) DEFAULT NULL,
  tipo ENUM('turno','cancelar','estudio') NOT NULL DEFAULT 'turno'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- Existing VPS DBs: run mysql/migrate_solicitudes_tipo.sql (init.sql is only applied on first MySQL volume).

INSERT INTO clinic_settings (id, address, clinic_hours, obras_sociales, welcome_text) VALUES (
  1,
  'Avenida Nicolas Avellaneda 347',
  'Lunes a Viernes de 9hs a 12hs y de 16hs a 19hs',
  JSON_ARRAY(
    'PAMI',
    'Subsidio de Salud',
    'Swiss Medical',
    'ASUNT',
    'Prensa',
    'Mora',
    'OSDE',
    'OSPAT',
    'OSFATUN'
  ),
  '¡Hola! Bienvenido/a a la Clínica Oftalmológica Artigas. ¿En qué te puedo ayudar?'
) ON DUPLICATE KEY UPDATE id = id;

INSERT INTO doctors (name, active, sort_order) VALUES
  ('Adrian Artigas', 1, 1),
  ('Esteban Artigas', 1, 2),
  ('Alejandro Artigas', 1, 3),
  ('Eduardo Artigas', 1, 4),
  ('Enrique Hector Artigas', 1, 5),
  ('Paulina Artigas', 1, 6);
