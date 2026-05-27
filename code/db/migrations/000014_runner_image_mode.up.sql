-- Adauga modul "image" pentru runner-ele plug-in: in loc sa incarce un script
-- Python (procesat de wrapper-ul runner-custom), super-adminul poate da direct
-- o referinta catre o imagine container construita extern. Cele doua moduri
-- sunt mutual exclusive si toate runner-ele existente raman valide (script_mode).

ALTER TABLE runners
    ALTER COLUMN script_content DROP NOT NULL;

ALTER TABLE runners
    ADD COLUMN IF NOT EXISTS image VARCHAR(255) NOT NULL DEFAULT '';

-- XOR: exact unul dintre script_content (non-empty) sau image (non-empty)
-- trebuie sa fie prezent. Asta permite migrarea celor existente (toate au
-- script_content non-empty si image='') si validarea celor noi.
ALTER TABLE runners
    ADD CONSTRAINT runners_source_check CHECK (
        (script_content IS NOT NULL AND script_content <> '' AND image = '')
        OR
        (image <> '' AND (script_content IS NULL OR script_content = ''))
    );
