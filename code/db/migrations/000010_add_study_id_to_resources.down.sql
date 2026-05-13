DROP INDEX IF EXISTS idx_simulation_runs_study_id;
DROP INDEX IF EXISTS idx_datasets_study_id;

ALTER TABLE simulation_runs DROP COLUMN IF EXISTS study_id;
ALTER TABLE datasets DROP COLUMN IF EXISTS study_id;
