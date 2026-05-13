CREATE TABLE IF NOT EXISTS simulation_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset_id    UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    model_type    VARCHAR(16) NOT NULL DEFAULT 'sidarthe',
    language      VARCHAR(16) NOT NULL,
    parameters    JSONB NOT NULL,
    population_n  BIGINT NOT NULL,
    t_max         INTEGER NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    CHECK (model_type IN ('sis', 'sir', 'seir', 'sirs', 'sidarthe')),
    CHECK (language IN ('r', 'julia', 'python')),
    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CHECK (jsonb_typeof(parameters) = 'object'),
    CHECK (population_n > 0),
    CHECK (t_max > 0)
);

CREATE INDEX IF NOT EXISTS idx_sim_runs_user_id ON simulation_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_sim_runs_dataset_id ON simulation_runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_sim_runs_status ON simulation_runs(status);
CREATE INDEX IF NOT EXISTS idx_sim_runs_language ON simulation_runs(language);
CREATE INDEX IF NOT EXISTS idx_sim_runs_model_type ON simulation_runs(model_type);
