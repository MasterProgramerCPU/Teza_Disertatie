CREATE TABLE IF NOT EXISTS studies (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    disease_code  VARCHAR(64) NOT NULL,
    description   TEXT,
    created_by    UUID NOT NULL REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_studies_disease_code ON studies(disease_code);
CREATE INDEX IF NOT EXISTS idx_studies_created_by ON studies(created_by);
