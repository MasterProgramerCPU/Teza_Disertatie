ALTER TABLE simulation_runs
    DROP CONSTRAINT IF EXISTS simulation_runs_model_type_check;

UPDATE simulation_runs
SET model_type = 'sidarthe'
WHERE model_type = 'sidarth';

-- Include si 'script' (adaugat de 000015), ca re-rularea pe DB matur sa nu
-- esueze. Comportamentul final dupa 000015 ramane identic.
ALTER TABLE simulation_runs
    ADD CONSTRAINT simulation_runs_model_type_check
    CHECK (model_type IN ('sis', 'sir', 'seir', 'sirs', 'sidarthe', 'lstm', 'script'));
