ALTER TABLE epidemiological_records
    DROP COLUMN IF EXISTS reproduction_rate,
    DROP COLUMN IF EXISTS stringency_index,
    DROP COLUMN IF EXISTS tested,
    DROP COLUMN IF EXISTS vaccinated,
    DROP COLUMN IF EXISTS icu,
    DROP COLUMN IF EXISTS hospitalized,
    DROP COLUMN IF EXISTS new_deaths,
    DROP COLUMN IF EXISTS new_cases,
    DROP COLUMN IF EXISTS deaths;
