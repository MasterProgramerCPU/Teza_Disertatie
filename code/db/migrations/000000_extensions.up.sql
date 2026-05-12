-- pgcrypto pentru gen_random_uuid(). Yugabyte 2024.1 e bazat pe PostgreSQL 11.2,
-- care nu are inca aceasta functie built-in (e introdusa in PG 13).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
