ALTER TABLE simulation_runs DROP CONSTRAINT IF EXISTS simulation_runs_t_max_check;
ALTER TABLE simulation_runs ADD CONSTRAINT simulation_runs_t_max_check
    CHECK (t_max > 0);
