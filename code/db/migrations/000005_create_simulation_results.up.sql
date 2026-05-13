CREATE TABLE IF NOT EXISTS simulation_results (
    simulation_id UUID NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    t             INTEGER NOT NULL,
    compartments  JSONB NOT NULL,
    PRIMARY KEY (simulation_id, t),
    CHECK (t >= 0),
    CHECK (jsonb_typeof(compartments) = 'object')
);
