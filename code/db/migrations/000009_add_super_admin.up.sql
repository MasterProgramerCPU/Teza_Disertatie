-- Adauga campul is_super_admin pe users si promoveaza primul user existent
-- (cel mai vechi created_at) la super admin daca nu exista inca niciunul.
-- Idempotent: la rulari repetate nu modifica nimic daca exista deja un super admin.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE users
SET is_super_admin = TRUE
WHERE id = (
    SELECT id FROM users ORDER BY created_at ASC LIMIT 1
)
AND NOT EXISTS (
    SELECT 1 FROM users WHERE is_super_admin = TRUE
);
