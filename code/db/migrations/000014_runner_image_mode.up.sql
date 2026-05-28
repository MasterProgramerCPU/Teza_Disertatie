-- Adauga modul "image" pentru runner-ele plug-in: in loc sa incarce un script
-- Python (procesat de wrapper-ul runner-custom), super-adminul poate da direct
-- o referinta catre o imagine container construita extern. Cele doua moduri
-- sunt mutual exclusive si toate runner-ele existente raman valide (script_mode).
--
-- NOTA: migratia 000015 ulterior dropeaza coloana script_content (pivotul:
-- runner-ele in mod script sunt eliminate, ramane doar mod image). Pentru ca
-- re-rularea job-ului de migrare pe un DB matur (post-15) sa nu esueze pe
-- referinte la script_content, incadram fiecare comanda intr-un bloc care o
-- executa doar daca coloana mai exista.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='runners' AND column_name='script_content'
    ) THEN
        ALTER TABLE runners ALTER COLUMN script_content DROP NOT NULL;
    END IF;
END $$;

ALTER TABLE runners
    ADD COLUMN IF NOT EXISTS image VARCHAR(255) NOT NULL DEFAULT '';

-- XOR: exact unul dintre script_content (non-empty) sau image (non-empty)
-- trebuie sa fie prezent. Asta permite migrarea celor existente (toate au
-- script_content non-empty si image='') si validarea celor noi. Pe DB matur
-- (post-15) coloana nu mai exista; constrangerea finala e instalata de 000015.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='runners' AND column_name='script_content'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='runners_source_check'
    ) THEN
        ALTER TABLE runners
            ADD CONSTRAINT runners_source_check CHECK (
                (script_content IS NOT NULL AND script_content <> '' AND image = '')
                OR
                (image <> '' AND (script_content IS NULL OR script_content = ''))
            );
    END IF;
END $$;
