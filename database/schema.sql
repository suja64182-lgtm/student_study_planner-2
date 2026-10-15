-- The application creates the same tables using SQLAlchemy with `flask --app app db`-free setup.
-- Create the database and least-privilege app user in MySQL before first start:
CREATE DATABASE IF NOT EXISTS student_study_planner CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- Tables are created safely if missing by `flask --app app init-db`; it never drops data.
