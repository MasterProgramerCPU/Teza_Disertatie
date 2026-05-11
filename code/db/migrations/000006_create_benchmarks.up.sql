CREATE TABLE benchmarks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id   UUID NOT NULL REFERENCES simulation_runs(id) ON DELETE CASCADE,
    wall_time_ms    BIGINT NOT NULL,
    cpu_time_ms     BIGINT NOT NULL,
    peak_memory_mb  REAL NOT NULL,
    CHECK (wall_time_ms >= 0),
    CHECK (cpu_time_ms >= 0),
    CHECK (peak_memory_mb >= 0)
);

CREATE INDEX idx_benchmarks_simulation_id ON benchmarks(simulation_id);
