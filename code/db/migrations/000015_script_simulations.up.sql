-- Pivot: scripturile nu mai sunt "runner-e" persistente, ci o forma de
-- simulare ad-hoc care ruleaza pe un executor partajat. Tabela runners ramane
-- strict pentru runner-ele persistente bazate pe imagine externa.

-- 1) Curatare runners: pastram doar runner-ele in mod image. Eventualele
--    runner-e in mod script sunt sterse (Deployment-urile lor au fost
--    deja oprite de testele anterioare).
DELETE FROM runners WHERE script_content IS NOT NULL AND image = '';

ALTER TABLE runners DROP CONSTRAINT IF EXISTS runners_source_check;
ALTER TABLE runners DROP COLUMN IF EXISTS script_content;

-- Acum image este strict obligatoriu.
ALTER TABLE runners ADD CONSTRAINT runners_image_required CHECK (image <> '');

-- 2) Extinderea simulation_runs cu script_content (nullable, doar pentru
--    simularile de tip 'script'). Plus extinderea CHECK-ului pe model_type.
ALTER TABLE simulation_runs ADD COLUMN IF NOT EXISTS script_content TEXT;

ALTER TABLE simulation_runs DROP CONSTRAINT IF EXISTS simulation_runs_model_type_check;
ALTER TABLE simulation_runs ADD CONSTRAINT simulation_runs_model_type_check
    CHECK (model_type IN ('sis', 'sir', 'seir', 'sirs', 'sidarthe', 'lstm', 'script'));

-- Coerenta: pentru model_type='script' script_content trebuie sa fie non-vid;
-- pentru celelalte trebuie sa fie NULL (sau lipsa).
ALTER TABLE simulation_runs ADD CONSTRAINT simulation_runs_script_content_check
    CHECK (
        (model_type = 'script' AND script_content IS NOT NULL AND script_content <> '')
        OR
        (model_type <> 'script' AND script_content IS NULL)
    );
