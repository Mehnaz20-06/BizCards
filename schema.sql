-- BizCardX database schema. Run once as the MySQL admin (root / avnadmin).
CREATE DATABASE IF NOT EXISTS bizcardx CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bizcardx;

CREATE TABLE IF NOT EXISTS users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(50)  NOT NULL UNIQUE,
  password_hash VARCHAR(100) NOT NULL,          -- bcrypt hash, never the password
  role          ENUM('admin','editor','viewer') NOT NULL DEFAULT 'viewer',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  full_name   VARCHAR(150),
  designation VARCHAR(150),
  company     VARCHAR(200),
  phones      VARCHAR(200),                     -- E.164, comma separated
  email       VARCHAR(200),
  website     VARCHAR(200),
  address     TEXT,
  raw_text    TEXT,                             -- what OCR read, for auditing
  image_hash  CHAR(16),                         -- perceptual hash, for duplicate checks
  created_by  INT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_name (full_name),
  INDEX idx_email (email),
  INDEX idx_hash (image_hash),
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  user_id    INT NOT NULL,
  action     VARCHAR(30) NOT NULL,              -- LOGIN, CREATE, UPDATE, DELETE, EXPORT
  contact_id INT NULL,
  details    VARCHAR(255),
  at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);