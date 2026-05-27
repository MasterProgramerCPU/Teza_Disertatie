package handlers

import (
	"encoding/csv"
	"errors"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"

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

// maxTMax limiteaza orizontul de integrare acceptat. Fara un plafon superior, un
// t_max arbitrar de mare ar genera integrari foarte lungi si scrieri masive in
// baza de date, deci o cale de epuizare a resurselor (DoS). Valoarea acopera
// orizonturile folosite in campania de benchmark (pana la 50000) cu marja.
const maxTMax = 100000

type createSimulationReq struct {
	DatasetID     uuid.UUID          `json:"dataset_id"`
	ModelType     string             `json:"model_type"`
	Language      string             `json:"language"`
	Parameters    map[string]float64 `json:"parameters"`
	PopulationN   *int64             `json:"population_n,omitempty"`
	TMax          int                `json:"t_max"`
	ScriptContent string             `json:"script_content,omitempty"`
}

// maxSimScriptBytes plafoneaza dimensiunea scriptului trimis intr-o simulare
// de tip 'script' (1 MB, suficient pentru orice notebook-cell-like).
const maxSimScriptBytes = 1 << 20

var defaultParameters = map[models.ModelType]map[string]float64{
	models.ModelSIS: {
		"beta":  0.3,
		"gamma": 0.0714,
	},
	models.ModelSIR: {
		"beta":  0.3,
		"gamma": 0.0714,
	},
	models.ModelSEIR: {
		"beta":  0.3,
		"sigma": 0.1923,
		"gamma": 0.0714,
	},
	models.ModelSIRS: {
		"beta":  0.3,
		"gamma": 0.0714,
		"xi":    0.0055,
	},
	models.ModelSIDARTHE: {
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
		"tau":     0.010,
	},
	models.ModelLSTM: {
		"lookback":      14,
		"hidden_size":   12,
		"epochs":        150,
		"learning_rate": 0.01,
	},
}

var requiredParameters = map[models.ModelType][]string{
	models.ModelSIS:  {"beta", "gamma"},
	models.ModelSIR:  {"beta", "gamma"},
	models.ModelSEIR: {"beta", "sigma", "gamma"},
	models.ModelSIRS: {"beta", "gamma", "xi"},
	models.ModelSIDARTHE: {
		"alpha", "beta", "gamma", "delta",
		"epsilon", "zeta", "lambda",
		"eta", "rho", "theta", "mu", "kappa", "nu", "xi", "sigma", "tau",
	},
	models.ModelLSTM: {"lookback", "hidden_size", "epochs", "learning_rate"},
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
	switch model {
	case models.ModelSIS, models.ModelSIR, models.ModelSEIR, models.ModelSIRS:
		if out["beta"] <= 0 {
			return nil, errors.New("beta must be > 0 for " + string(model))
		}
		if out["gamma"] <= 0 {
			return nil, errors.New("gamma must be > 0 for " + string(model))
		}
	}
	if model == models.ModelSEIR && out["sigma"] <= 0 {
		return nil, errors.New("sigma must be > 0 for seir")
	}
	if model == models.ModelSIDARTHE && out["alpha"]+out["beta"]+out["gamma"]+out["delta"] <= 0 {
		return nil, errors.New("at least one SIDARTHE transmission parameter must be > 0")
	}
	if model == models.ModelLSTM {
		if err := validateIntegerParameter(out, "lookback", 2, 90); err != nil {
			return nil, err
		}
		if err := validateIntegerParameter(out, "hidden_size", 1, 128); err != nil {
			return nil, err
		}
		if err := validateIntegerParameter(out, "epochs", 1, 5000); err != nil {
			return nil, err
		}
		if out["learning_rate"] <= 0 || out["learning_rate"] > 1 {
			return nil, errors.New("learning_rate must be in (0, 1] for lstm")
		}
	}
	return out, nil
}

func validateIntegerParameter(params map[string]float64, key string, min, max int) error {
	value := params[key]
	if value != math.Trunc(value) {
		return errors.New(key + " must be an integer")
	}
	if value < float64(min) || value > float64(max) {
		return errors.New(key + " must be between " + strconv.Itoa(min) + " and " + strconv.Itoa(max))
	}
	return nil
}

func initialCompartments(model models.ModelType, popN int64, first *models.EpidemiologicalRecord) map[string]float64 {
	i0 := float64(first.Infected)
	removed0 := 0.0
	if first.Recovered != nil {
		removed0 = float64(*first.Recovered)
	}
	s0 := float64(popN) - i0 - removed0
	if first.Susceptible != nil {
		s0 = float64(*first.Susceptible)
	}

	switch model {
	case models.ModelSIS:
		return map[string]float64{"s": s0 + removed0, "i": i0}
	case models.ModelSIR, models.ModelSIRS:
		return map[string]float64{"s": s0, "i": i0, "r": removed0}
	case models.ModelSEIR:
		return map[string]float64{"s": s0, "e": 0, "i": i0, "r": removed0}
	case models.ModelSIDARTHE:
		return map[string]float64{
			"s": s0,
			"i": i0,
			"d": 0,
			"a": 0,
			"r": 0,
			"t": 0,
			"h": removed0,
			"e": 0,
		}
	case models.ModelLSTM:
		return map[string]float64{"observed": i0}
	default:
		return map[string]float64{"s": s0, "i": i0, "r": removed0}
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
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
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
		req.ModelType = string(models.ModelSIDARTHE)
	}
	if !models.ValidModelType(req.ModelType) {
		writeError(w, http.StatusBadRequest, "model_type must be one of "+supportedModelTypesString())
		return
	}
	modelType := models.ModelType(req.ModelType)

	// Script-mode urmeaza o cale separata: dispecerizat la executorul partajat
	// runner-script, fara validari de model/limbaj/t_max/initial-conditions.
	// Scriptul decide singur orizontul (poate ignora t_max).
	if modelType == models.ModelScript {
		h.createScriptSimulation(w, r, sid, uid, &req)
		return
	}

	if req.TMax <= 0 {
		writeError(w, http.StatusBadRequest, "t_max must be > 0")
		return
	}
	if req.TMax > maxTMax {
		writeError(w, http.StatusBadRequest, "t_max exceeds maximum of "+strconv.Itoa(maxTMax))
		return
	}

	if !models.ValidLanguage(req.Language) {
		writeError(w, http.StatusBadRequest, "language must be one of r, julia, python")
		return
	}
	if modelType == models.ModelLSTM && models.Language(req.Language) != models.LangPython {
		writeError(w, http.StatusBadRequest, "lstm is executed by the dedicated LSTM runner and must use language=python")
		return
	}
	parameters, err := normalizedParameters(modelType, req.Parameters)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	dataset, err := h.datasets.Get(r.Context(), sid, req.DatasetID)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "dataset not found in study")
			return
		}
		writeError(w, http.StatusInternalServerError, "dataset lookup failure")
		return
	}
	if modelType == models.ModelLSTM && dataset.RecordCount <= int(parameters["lookback"]) {
		writeError(w, http.StatusBadRequest, "dataset must contain more records than lookback for lstm")
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
		StudyID:     sid,
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
	dispatchTarget := req.Language
	if modelType == models.ModelLSTM {
		dispatchTarget = "lstm"
	}
	if err := h.dispatcher.Publish(r.Context(), dispatchTarget, msg); err != nil {
		writeError(w, http.StatusInternalServerError, "could not dispatch job: "+err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, created)
}

// createScriptSimulation gestioneaza simularile de tip 'script': scriptul user
// este pasat odata cu jobul si executat de runner-script. Spre deosebire de
// caile compartimentale, aici nu calculam initial conditions si nu validam
// parametri prin schema fixa --- scriptul interpreteaza singur ce primeste.
func (h *SimulationsHandler) createScriptSimulation(w http.ResponseWriter, r *http.Request,
	sid, uid uuid.UUID, req *createSimulationReq) {

	if strings.TrimSpace(req.ScriptContent) == "" {
		writeError(w, http.StatusBadRequest, "script_content required for model_type='script'")
		return
	}
	if len(req.ScriptContent) > maxSimScriptBytes {
		writeError(w, http.StatusBadRequest, "script_content exceeds maximum size of 1 MB")
		return
	}
	if _, err := h.datasets.Get(r.Context(), sid, req.DatasetID); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "dataset not found in study")
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

	run := &models.SimulationRun{
		UserID:        uid,
		StudyID:       sid,
		DatasetID:     req.DatasetID,
		ModelType:     models.ModelScript,
		Language:      models.LangPython,
		Parameters:    req.Parameters,
		PopulationN:   popN,
		TMax:          req.TMax,
		ScriptContent: req.ScriptContent,
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
		SimulationID:  created.ID,
		DatasetID:     req.DatasetID,
		ModelType:     string(models.ModelScript),
		Parameters:    req.Parameters,
		PopulationN:   popN,
		TMax:          req.TMax,
		DBDSN:         dsn,
		ScriptContent: req.ScriptContent,
	}
	if err := h.dispatcher.Publish(r.Context(), "script", msg); err != nil {
		writeError(w, http.StatusInternalServerError, "could not dispatch script job: "+err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

func (h *SimulationsHandler) List(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	out, err := h.sims.ListByStudy(r.Context(), sid)
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
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	s, err := h.sims.Get(r.Context(), sid, id)
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
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if _, err := h.sims.Get(r.Context(), sid, id); err != nil {
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
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if _, err := h.sims.Get(r.Context(), sid, id); err != nil {
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
	preferred := []string{"s", "i", "d", "a", "r", "t", "h", "e"}
	if seen["e"] && !seen["d"] && !seen["a"] && !seen["t"] && !seen["h"] {
		preferred = []string{"s", "e", "i", "r"}
	}
	if seen["observed"] || seen["fitted"] || seen["predicted"] {
		preferred = []string{"observed", "fitted", "predicted"}
	}
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

func supportedModelTypesString() string {
	types := make([]string, 0, len(models.SupportedModelTypes))
	for _, model := range models.SupportedModelTypes {
		types = append(types, string(model))
	}
	return strings.Join(types, ", ")
}
