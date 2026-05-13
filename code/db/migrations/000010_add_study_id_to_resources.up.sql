-- Adauga study_id la dataseturi si simulari. NOT NULL pentru consistenta —
-- presupunem ca nu exista date pre-existente (cluster fresh) sau ca un studiu
-- default e creat manual inainte de migrare in mediile cu date.
ALTER TABLE datasets
    ADD COLUMN IF NOT EXISTS study_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE;

ALTER TABLE simulation_runs
    ADD COLUMN IF NOT EXISTS study_id UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_datasets_study_id ON datasets(study_id);
CREATE INDEX IF NOT EXISTS idx_simulation_runs_study_id ON simulation_runs(study_id);
