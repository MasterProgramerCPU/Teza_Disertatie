-- Tabel pentru runner-ele de algoritmi definiți de utilizator (plug-in-uri).
-- Fiecare runner este scope-uit la un singur studiu și poate fi creat doar de
-- un super-admin. Scriptul (entry.py) este stocat ca text in baza de date.
-- Runner-ul trece prin starile: pending -> building -> ready -> stopped/failed.

CREATE TABLE IF NOT EXISTS runners (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id         UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    uploaded_by      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name             VARCHAR(128) NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    script_content   TEXT NOT NULL,
    parameter_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           VARCHAR(32) NOT NULL DEFAULT 'pending',
    status_message   TEXT NOT NULL DEFAULT '',
    image_tag        VARCHAR(255) NOT NULL DEFAULT '',
    queue_name       VARCHAR(128) NOT NULL,
    deployment_name  VARCHAR(128) NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at         TIMESTAMPTZ,
    CHECK (status IN ('pending', 'building', 'ready', 'failed', 'stopped'))
);

CREATE INDEX IF NOT EXISTS idx_runners_study_id ON runners(study_id);
CREATE INDEX IF NOT EXISTS idx_runners_status ON runners(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_runners_study_name ON runners(study_id, name);
