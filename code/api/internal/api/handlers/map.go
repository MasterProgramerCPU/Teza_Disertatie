package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
)

// MapHandler expune datele necesare paginii de harta: pentru fiecare dataset
// (= o tara) dintr-un studiu, seria observata si — daca exista o simulare
// completata pentru combinatia (model, limbaj) — seria simulata corespunzatoare.
type MapHandler struct {
	pool *pgxpool.Pool
}

func NewMapHandler(pool *pgxpool.Pool) *MapHandler {
	return &MapHandler{pool: pool}
}

type mapSeries struct {
	StartDate string    `json:"start_date"` // ISO YYYY-MM-DD
	Values    []float64 `json:"values"`
}

type simMeta struct {
	ID         uuid.UUID `json:"id"`
	CreatedAt  time.Time `json:"created_at"`
	TMax       int       `json:"t_max"`
	TotalRuns  int       `json:"total_runs"` // câte rulări completate există pentru combinație
}

type mapCountry struct {
	DatasetID    uuid.UUID  `json:"dataset_id"`
	Name         string     `json:"name"`
	ISO3         string     `json:"iso3"`
	Population   int64      `json:"population"`
	Observed     mapSeries  `json:"observed"`
	Simulated    *mapSeries `json:"simulated,omitempty"`
	SimulationID *uuid.UUID `json:"simulation_id,omitempty"`
	Simulation   *simMeta   `json:"simulation,omitempty"`
}

type mapResponse struct {
	StudyID      uuid.UUID    `json:"study_id"`
	ModelType    string       `json:"model_type"`
	Language     string       `json:"language"`
	Countries    []mapCountry `json:"countries"`
	GlobalMinDay string       `json:"global_min_day,omitempty"`
	GlobalMaxDay string       `json:"global_max_day,omitempty"`
}

// Get returneaza date pentru harta studiului. Parametrii model+language sunt
// optionali — daca lipsesc, doar seriile observate sunt populate (simulated nil).
func (h *MapHandler) Get(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	model := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("model")))
	lang := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("language")))

	ctx := r.Context()

	// 1. dataseturi din studiu, cu ISO3 (= region_code din primul rand)
	const dsQ = `
		WITH first_region AS (
			SELECT DISTINCT ON (dataset_id)
				dataset_id, region_code, population
			FROM epidemiological_records
			ORDER BY dataset_id, recorded_date ASC
		)
		SELECT d.id, d.name, fr.region_code, fr.population
		FROM datasets d
		JOIN first_region fr ON fr.dataset_id = d.id
		WHERE d.study_id = $1
		ORDER BY d.name`
	rows, err := h.pool.Query(ctx, dsQ, sid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "datasets query: "+err.Error())
		return
	}
	type dsRow struct {
		ID    uuid.UUID
		Name  string
		ISO3  string
		Popul int64
	}
	var dsList []dsRow
	for rows.Next() {
		var d dsRow
		if err := rows.Scan(&d.ID, &d.Name, &d.ISO3, &d.Popul); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "datasets scan: "+err.Error())
			return
		}
		dsList = append(dsList, d)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "datasets rows: "+err.Error())
		return
	}

	countries := make([]mapCountry, 0, len(dsList))
	var globalMin, globalMax time.Time
	setBound := func(t time.Time) {
		if globalMin.IsZero() || t.Before(globalMin) {
			globalMin = t
		}
		if globalMax.IsZero() || t.After(globalMax) {
			globalMax = t
		}
	}

	for _, d := range dsList {
		obs, err := loadObserved(ctx, h.pool, d.ID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "observed: "+err.Error())
			return
		}
		c := mapCountry{
			DatasetID:  d.ID,
			Name:       d.Name,
			ISO3:       d.ISO3,
			Population: d.Popul,
			Observed:   obs,
		}
		if t, err := time.Parse("2006-01-02", obs.StartDate); err == nil && len(obs.Values) > 0 {
			setBound(t)
			setBound(t.AddDate(0, 0, len(obs.Values)-1))
		}

		if model != "" && lang != "" {
			sim, meta, err := loadSimulated(ctx, h.pool, sid, d.ID, model, lang)
			if err != nil {
				log.Printf("map: loadSimulated study=%s dataset=%s model=%s lang=%s err=%v",
					sid, d.ID, model, lang, err)
				// Nu intoarcem 500 — datele observate sunt deja valide;
				// frontend-ul afiseaza banner cand simulated lipseste.
			} else if sim != nil && meta != nil {
				c.Simulated = sim
				simID := meta.ID
				c.SimulationID = &simID
				c.Simulation = meta
				if t, err := time.Parse("2006-01-02", sim.StartDate); err == nil && len(sim.Values) > 0 {
					setBound(t)
					setBound(t.AddDate(0, 0, len(sim.Values)-1))
				}
			}
		}
		countries = append(countries, c)
	}

	resp := mapResponse{
		StudyID:   sid,
		ModelType: model,
		Language:  lang,
		Countries: countries,
	}
	if !globalMin.IsZero() {
		resp.GlobalMinDay = globalMin.Format("2006-01-02")
	}
	if !globalMax.IsZero() {
		resp.GlobalMaxDay = globalMax.Format("2006-01-02")
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"data": resp})
}

func loadObserved(ctx context.Context, pool *pgxpool.Pool, datasetID uuid.UUID) (mapSeries, error) {
	const q = `
		SELECT recorded_date, infected
		FROM epidemiological_records
		WHERE dataset_id = $1
		ORDER BY recorded_date ASC`
	rows, err := pool.Query(ctx, q, datasetID)
	if err != nil {
		return mapSeries{}, err
	}
	defer rows.Close()
	var dates []time.Time
	var vals []float64
	for rows.Next() {
		var t time.Time
		var v int64
		if err := rows.Scan(&t, &v); err != nil {
			return mapSeries{}, err
		}
		dates = append(dates, t)
		vals = append(vals, float64(v))
	}
	if err := rows.Err(); err != nil {
		return mapSeries{}, err
	}
	if len(dates) == 0 {
		return mapSeries{Values: []float64{}}, nil
	}
	return mapSeries{StartDate: dates[0].Format("2006-01-02"), Values: vals}, nil
}

// loadSimulated: gaseste cea mai recenta simulare completata pentru
// (study, dataset, model, language) si extrage seria "I" sau "infected" din
// fiecare punct temporal. StartDate = data primei zile cu cazuri reale din
// dataset (acelasi punct pe care API-ul a folosit-o ca conditie initiala).
// Returneaza si metadate (created_at, t_max, total runs) pentru a fi expuse
// in UI — utilizatorul vrea sa stie care dintre rulari e afisata pe harta.
func loadSimulated(
	ctx context.Context, pool *pgxpool.Pool,
	studyID, datasetID uuid.UUID, model, lang string,
) (*mapSeries, *simMeta, error) {
	const simQ = `
		SELECT s.id, s.created_at, s.t_max
		FROM simulation_runs s
		WHERE s.study_id = $1 AND s.dataset_id = $2
		  AND s.model_type = $3 AND s.language = $4
		  AND s.status = 'completed'
		ORDER BY s.created_at DESC
		LIMIT 1`
	var meta simMeta
	err := pool.QueryRow(ctx, simQ, studyID, datasetID, model, lang).Scan(
		&meta.ID, &meta.CreatedAt, &meta.TMax,
	)
	if err != nil {
		// Lipsa unei simulari completate pentru combinatia ceruta nu e o eroare —
		// raspundem cu simulated=nil si frontend-ul afiseaza un banner.
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil, nil
		}
		// Orice alta eroare (DB down, sintaxa, etc.) e reala — o propagam.
		return nil, nil, err
	}

	// Numarul total de rulari completate pentru aceasta combinatie — afisat
	// in UI ca "1 din N rulari".
	const countQ = `
		SELECT COUNT(*) FROM simulation_runs
		WHERE study_id = $1 AND dataset_id = $2
		  AND model_type = $3 AND language = $4 AND status = 'completed'`
	_ = pool.QueryRow(ctx, countQ, studyID, datasetID, model, lang).Scan(&meta.TotalRuns)

	const startQ = `
		SELECT MIN(recorded_date)
		FROM epidemiological_records
		WHERE dataset_id = $1 AND infected > 0`
	var start *time.Time
	if err := pool.QueryRow(ctx, startQ, datasetID).Scan(&start); err != nil {
		return nil, nil, err
	}
	if start == nil {
		// fallback: prima zi a dataset-ului
		const firstQ = `SELECT MIN(recorded_date) FROM epidemiological_records WHERE dataset_id = $1`
		if err := pool.QueryRow(ctx, firstQ, datasetID).Scan(&start); err != nil {
			return nil, nil, err
		}
		if start == nil {
			return nil, nil, nil
		}
	}

	const valQ = `
		SELECT t, compartments
		FROM simulation_results
		WHERE simulation_id = $1
		ORDER BY t ASC`
	rows, err := pool.Query(ctx, valQ, meta.ID)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	var vals []float64
	for rows.Next() {
		var t int
		var raw json.RawMessage
		if err := rows.Scan(&t, &raw); err != nil {
			return nil, nil, err
		}
		var comp map[string]float64
		if err := json.Unmarshal(raw, &comp); err != nil {
			continue
		}
		val := 0.0
		switch {
		case hasKey(comp, "i"):
			val = comp["i"]
		case hasKey(comp, "I"):
			val = comp["I"]
		case hasKey(comp, "infected"):
			val = comp["infected"]
		}
		vals = append(vals, val)
	}
	if err := rows.Err(); err != nil {
		return nil, nil, err
	}
	if len(vals) == 0 {
		return nil, nil, nil
	}
	return &mapSeries{
		StartDate: start.Format("2006-01-02"),
		Values:    vals,
	}, &meta, nil
}

func hasKey(m map[string]float64, k string) bool {
	_, ok := m[k]
	return ok
}
