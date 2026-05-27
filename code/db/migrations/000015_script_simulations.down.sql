ALTER TABLE simulation_runs DROP CONSTRAINT IF EXISTS simulation_runs_script_content_check;
ALTER TABLE simulation_runs DROP CONSTRAINT IF EXISTS simulation_runs_model_type_check;
ALTER TABLE simulation_runs ADD CONSTRAINT simulation_runs_model_type_check
    CHECK (model_type IN ('sis', 'sir', 'seir', 'sirs', 'sidarthe', 'lstm'));
ALTER TABLE simulation_runs DROP COLUMN IF EXISTS script_content;

ALTER TABLE runners DROP CONSTRAINT IF EXISTS runners_image_required;
ALTER TABLE runners ADD COLUMN IF NOT EXISTS script_content TEXT;
ALTER TABLE runners ADD CONSTRAINT runners_source_check CHECK (
    (script_content IS NOT NULL AND script_content <> '' AND image = '')
    OR
    (image <> '' AND (script_content IS NULL OR script_content = ''))
);
