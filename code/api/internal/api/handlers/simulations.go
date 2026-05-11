package handlers

import (
	"encoding/csv"
	"errors"
	"net/http"
	"os"
	"sort"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
	"github.com/tudorgeana/emedicine-api/internal/runner"
)

type SimulationsHandler struct {
	sims       *repository.SimulationRepository
	datasets   *repository.DatasetRepository
	results    *repository.ResultsRepository
	benches    *repository.BenchmarkRepository
	dispatcher *runner.Dispatcher
}

func NewSimulationsHandler(
	sims *repository.SimulationRepository,
	datasets *repository.DatasetRepository,
	results *repository.ResultsRepository,
	benches *repository.BenchmarkRepository,
	dispatcher *runner.Dispatcher,
) *SimulationsHandler {
	return &SimulationsHandler{
		sims: sims, datasets: datasets, results: results,
		benches: benches, dispatcher: dispatcher,
	}
}

type createSimulationReq struct {
	DatasetID   uuid.UUID          `json:"dataset_id"`
	ModelType   string             `json:"model_type"`
	Language    string             `json:"language"`
	Parameters  map[string]float64 `json:"parameters"`
	PopulationN *int64             `json:"population_n,omitempty"`
	TMax        int                `json:"t_max"`
}

var defaultParameters = map[models.ModelType]map[string]float64{
	models.ModelSIDARTH: {
		"alpha":   0.57,
		"beta":    0.011,
		"gamma":   0.456,
		"delta":   0.011,
		"epsilon": 0.171,
		"zeta":    0.125,
		"lambda":  0.034,
		"eta":     0.125,
		"rho":     0.034,
		"theta":   0.370,
		"mu":      0.017,
		"kappa":   0.017,
		"nu":      0.027,
		"xi":      0.017,
		"sigma":   0.017,
	},
	models.ModelSIR: {
		"beta":  0.3,
		"gamma": 0.0714,
	},
}

var requiredParameters = map[models.ModelType][]string{
	models.ModelSIDARTH: {
		"alpha", "beta", "gamma", "delta",
		"epsilon", "zeta", "lambda",
		"eta", "rho", "theta", "mu", "kappa", "nu", "xi", "sigma",
	},
	models.ModelSIR: {"beta", "gamma"},
}

func normalizedParameters(model models.ModelType, input map[string]float64) (map[string]float64, error) {
	out := map[string]float64{}
	for k, v := range defaultParameters[model] {
		out[k] = v
	}
	for k, v := range input {
		out[k] = v
	}
	for _, k := range requiredParameters[model] {
		v, ok := out[k]
		if !ok {
			return nil, errors.New("missing parameter: " + k)
		}
		if v < 0 {
			return nil, errors.New("parameter must be >= 0: " + k)
		}
	}
	if model == models.ModelSIR && (out["beta"] <= 0 || out["gamma"] <= 0) {
		return nil, errors.New("beta and gamma must be > 0 for SIR")
	}
	if model == models.ModelSIDARTH && out["alpha"]+out["beta"]+out["gamma"]+out["delta"] <= 0 {
		return nil, errors.New("at least one SIDARTH transmission parameter must be > 0")
	}
	return out, nil
}

func initialCompartments(model models.ModelType, popN int64, first *models.EpidemiologicalRecord) map[string]float64 {
	i0 := float64(first.Infected)
	h0 := 0.0
	if first.Recovered != nil {
		h0 = float64(*first.Recovered)
	}
	s0 := float64(popN) - i0 - h0
	if first.Susceptible != nil {
		s0 = float64(*first.Susceptible)
	}

	if model == models.ModelSIR {
		return map[string]float64{"s": s0, "i": i0, "r": h0}
	}
	return map[string]float64{
		"s": s0,
		"i": i0,
		"d": 0,
		"a": 0,
		"r": 0,
		"t": 0,
		"h": h0,
	}
}

func validateInitialCompartments(initial map[string]float64) error {
	for key, value := range initial {
		if value < 0 {
			return errors.New("initial compartment must be >= 0: " + key)
		}
	}
	return nil
}

func (h *SimulationsHandler) Create(w http.ResponseWriter, r *http.Request) {
	uid, _ := authmw.UserIDFrom(r.Context())

	var req createSimulationReq
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}

	if req.DatasetID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "dataset_id required")
		return
	}
	if req.ModelType == "" {
		req.ModelType = string(models.ModelSIDARTH)
	}
	if !models.ValidModelType(req.ModelType) {
		writeError(w, http.StatusBadRequest, "model_type must be one of sidarth, sir")
		return
	}
	if !models.ValidLanguage(req.Language) {
		writeError(w, http.StatusBadRequest, "language must be one of r, julia, python")
		return
	}
	if req.TMax <= 0 {
		writeError(w, http.StatusBadRequest, "t_max must be > 0")
		return
	}
	modelType := models.ModelType(req.ModelType)
	parameters, err := normalizedParameters(modelType, req.Parameters)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	if _, err := h.datasets.Get(r.Context(), uid, req.DatasetID); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "dataset not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "dataset lookup failure")
		return
	}

	first, err := h.datasets.FirstRecord(r.Context(), req.DatasetID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "dataset has no records")
		return
	}

	popN := first.Population
	if req.PopulationN != nil && *req.PopulationN > 0 {
		popN = *req.PopulationN
	}
	initial := initialCompartments(modelType, popN, first)
	if err := validateInitialCompartments(initial); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	run := &models.SimulationRun{
		UserID:      uid,
		DatasetID:   req.DatasetID,
		ModelType:   modelType,
		Language:    models.Language(req.Language),
		Parameters:  parameters,
		PopulationN: popN,
		TMax:        req.TMax,
	}
	created, err := h.sims.Create(r.Context(), run)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not create simulation: "+err.Error())
		return
	}

	dsn := os.Getenv("RUNNER_DATABASE_URL")
	if dsn == "" {
		dsn = os.Getenv("DATABASE_URL")
	}

	msg := &runner.JobMessage{
		SimulationID: created.ID,
		DatasetID:    req.DatasetID,
		ModelType:    string(modelType),
		Parameters:   parameters,
		PopulationN:  popN,
		TMax:         req.TMax,
		Initial:      initial,
		DBDSN:        dsn,
	}
	if err := h.dispatcher.Publish(r.Context(), req.Language, msg); err != nil {
		writeError(w, http.StatusInternalServerError, "could not dispatch job: "+err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, created)
}

func (h *SimulationsHandler) List(w http.ResponseWriter, r *http.Request) {
	uid, _ := authmw.UserIDFrom(r.Context())
	out, err := h.sims.ListByUser(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not list simulations")
		return
	}
	if out == nil {
		out = []models.SimulationRun{}
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *SimulationsHandler) Get(w http.ResponseWriter, r *http.Request) {
	uid, _ := authmw.UserIDFrom(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	s, err := h.sims.Get(r.Context(), uid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "simulation not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failure")
		return
	}
	writeJSON(w, http.StatusOK, s)
}

func (h *SimulationsHandler) Results(w http.ResponseWriter, r *http.Request) {
	uid, _ := authmw.UserIDFrom(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if _, err := h.sims.Get(r.Context(), uid, id); err != nil {
		writeError(w, http.StatusNotFound, "simulation not found")
		return
	}
	out, err := h.results.ListBySimulation(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "results query failure")
		return
	}
	if out == nil {
		out = []models.SimulationResult{}
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *SimulationsHandler) Export(w http.ResponseWriter, r *http.Request) {
	uid, _ := authmw.UserIDFrom(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if _, err := h.sims.Get(r.Context(), uid, id); err != nil {
		writeError(w, http.StatusNotFound, "simulation not found")
		return
	}
	out, err := h.results.ListBySimulation(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "results query failure")
		return
	}

	w.Header().Set("Content-Type", "text/csv")
	w.Header().Set("Content-Disposition", `attachment; filename="simulation_`+id.String()+`.csv"`)
	cw := csv.NewWriter(w)
	defer cw.Flush()
	keys := resultCompartmentKeys(out)
	header := append([]string{"t"}, keys...)
	_ = cw.Write(header)
	for _, row := range out {
		record := []string{strconv.Itoa(row.T)}
		for _, key := range keys {
			record = append(record, strconv.FormatFloat(row.Compartments[key], 'f', -1, 64))
		}
		_ = cw.Write(record)
	}
}

func resultCompartmentKeys(rows []models.SimulationResult) []string {
	seen := map[string]bool{}
	for _, row := range rows {
		for key := range row.Compartments {
			seen[key] = true
		}
	}
	preferred := []string{"s", "i", "d", "a", "r", "t", "h"}
	var keys []string
	for _, key := range preferred {
		if seen[key] {
			keys = append(keys, key)
			delete(seen, key)
		}
	}
	var extra []string
	for key := range seen {
		extra = append(extra, key)
	}
	sort.Strings(extra)
	return append(keys, extra...)
}
