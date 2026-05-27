-- Pentru simularile de tip 'script', t_max este metadata optionala (scriptul
-- isi alege orizontul singur). Pentru celelalte tipuri ramane obligatorie.
ALTER TABLE simulation_runs DROP CONSTRAINT IF EXISTS simulation_runs_t_max_check;
ALTER TABLE simulation_runs ADD CONSTRAINT simulation_runs_t_max_check
    CHECK ((model_type = 'script') OR (t_max > 0));
