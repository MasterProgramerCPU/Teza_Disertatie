-- Extindere schema epidemiological_records cu coloane suplimentare folosite
-- frecvent in literatura si in seturile OWID/WHO/ECDC, dincolo de cele 4
-- coloane SIR-centrice initiale (susceptible/infected/recovered/population).
-- Toate sunt nullable pentru ca nu orice dataset le include simultan.
-- Runner-ii built-in (SIR/SIDARTHE/LSTM) le ignora silentios; scripturile
-- definite de utilizator au acces la toate prin records[i] in main().

ALTER TABLE epidemiological_records
    ADD COLUMN IF NOT EXISTS deaths             BIGINT,    -- decese cumulate
    ADD COLUMN IF NOT EXISTS new_cases          BIGINT,    -- cazuri noi (interval = granularitatea dataset-ului)
    ADD COLUMN IF NOT EXISTS new_deaths         BIGINT,    -- decese noi (interval ca mai sus)
    ADD COLUMN IF NOT EXISTS hospitalized       BIGINT,    -- pacienti spitalizati la moment
    ADD COLUMN IF NOT EXISTS icu                BIGINT,    -- pacienti in terapie intensiva la moment
    ADD COLUMN IF NOT EXISTS vaccinated         BIGINT,    -- persoane vaccinate (cel putin o doza) cumulat
    ADD COLUMN IF NOT EXISTS tested             BIGINT,    -- teste cumulate
    ADD COLUMN IF NOT EXISTS stringency_index   REAL,      -- Oxford Stringency Index, 0..100
    ADD COLUMN IF NOT EXISTS reproduction_rate  REAL;      -- Rt observat (cand este disponibil)
