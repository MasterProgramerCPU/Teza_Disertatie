ALTER TABLE simulation_runs
    DROP CONSTRAINT IF EXISTS simulation_runs_model_type_check;

UPDATE simulation_runs
SET model_type = 'sidarthe'
WHERE model_type = 'sidarth';

-- Include si valorile adaugate de migratiile ulterioare (000012: 'lstm',
-- 000015: 'script') — altfel re-rularea job-ului pe un DB matur esueaza pe
-- randurile existente cu acele valori. Comportamentul final (dupa 000015)
-- ramane identic.
ALTER TABLE simulation_runs
    ADD CONSTRAINT simulation_runs_model_type_check
    CHECK (model_type IN ('sis', 'sir', 'seir', 'sirs', 'sidarthe', 'lstm', 'script'));
