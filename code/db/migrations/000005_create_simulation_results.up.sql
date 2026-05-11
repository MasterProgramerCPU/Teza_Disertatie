CREATE TABLE simulation_results (
    simulation_id UUID NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    t             INTEGER NOT NULL,
    s             DOUBLE PRECISION NOT NULL,
    i             DOUBLE PRECISION NOT NULL,
    r             DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (simulation_id, t),
    CHECK (t >= 0),
    CHECK (s >= 0),
    CHECK (i >= 0),
    CHECK (r >= 0)
);
