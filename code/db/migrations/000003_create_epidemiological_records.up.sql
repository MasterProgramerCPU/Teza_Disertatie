CREATE TABLE IF NOT EXISTS epidemiological_records (
    id            UUID DEFAULT gen_random_uuid(),
    dataset_id    UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    recorded_date DATE NOT NULL,
    region_code   VARCHAR(10) NOT NULL,
    susceptible   BIGINT,
    infected      BIGINT NOT NULL,
    recovered     BIGINT,
    population    BIGINT NOT NULL,
    PRIMARY KEY (dataset_id, recorded_date, id),
    CHECK (infected >= 0),
    CHECK (population > 0),
    CHECK (recovered IS NULL OR recovered >= 0),
    CHECK (susceptible IS NULL OR susceptible >= 0)
);

CREATE INDEX IF NOT EXISTS idx_epi_records_region ON epidemiological_records(region_code);
