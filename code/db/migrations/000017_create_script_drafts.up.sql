-- Draft-uri de cod pentru editorul de scripturi din UI. Fiecare cercetator are
-- propriile draft-uri per studiu si nu vede draft-urile altor utilizatori.
-- Continutul este pastrat ca text in DB (scripturi <1 MB tipic); pentru scale-up
-- la sute de MB per draft, datele pot fi mutate la stocare obiect (S3/MinIO),
-- mentinand metadatele in tabela.

CREATE TABLE IF NOT EXISTS script_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    study_id        UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    name            VARCHAR(128) NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    script_content  TEXT NOT NULL,
    parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_script_drafts_user_study ON script_drafts(user_id, study_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_script_drafts_user_study_name ON script_drafts(user_id, study_id, name);
