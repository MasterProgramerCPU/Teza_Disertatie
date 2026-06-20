-- Profil utilizator: coloane suplimentare pe users pentru pagina de profil.
-- Toate sunt nullable; un cont vechi care nu si-a completat profilul ramane
-- functional, iar API-ul intoarce sirurile goale daca lipsesc.
-- avatar_data tine binarul imaginii (max ~256KB dupa resize in browser).
-- avatar_mime fixeaza tipul (image/jpeg sau image/png).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS full_name    VARCHAR(160),
    ADD COLUMN IF NOT EXISTS affiliation  VARCHAR(200),
    ADD COLUMN IF NOT EXISTS bio          VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS avatar_data  BYTEA,
    ADD COLUMN IF NOT EXISTS avatar_mime  VARCHAR(32);
