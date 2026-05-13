CREATE TABLE IF NOT EXISTS study_members (
    study_id   UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       VARCHAR(32) NOT NULL,
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (study_id, user_id),
    CHECK (role IN ('admin', 'researcher', 'contributor', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_study_members_user_id ON study_members(user_id);
CREATE INDEX IF NOT EXISTS idx_study_members_role ON study_members(role);
