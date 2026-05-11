package handlers

import (
	"encoding/csv"
	"errors"
	"net/http"
	"os"
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
	DatasetID   uuid.UUID `json:"dataset_id"`
	Language    string    `json:"language"`
	Beta        float64   `json:"beta"`
	Gamma       float64   `json:"gamma"`
	PopulationN *int64    `json:"population_n,omitempty"`
	TMax        int       `json:"t_max"`
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
	if !models.ValidLanguage(req.Language) {
		writeError(w, http.StatusBadRequest, "language must be one of r, julia, python")
		return
	}
	if req.Beta <= 0 || req.Gamma <= 0 || req.TMax <= 0 {
		writeError(w, http.StatusBadRequest, "beta, gamma, t_max must be > 0")
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

	i0 := float64(first.Infected)
	r0 := 0.0
	if first.Recovered != nil {
		r0 = float64(*first.Recovered)
	}
	s0 := float64(popN) - i0 - r0
	if first.Susceptible != nil {
		s0 = float64(*first.Susceptible)
	}

	run := &models.SimulationRun{
		UserID:      uid,
		DatasetID:   req.DatasetID,
		Language:    models.Language(req.Language),
		Beta:        req.Beta,
		Gamma:       req.Gamma,
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
		Beta:         req.Beta,
		Gamma:        req.Gamma,
		PopulationN:  popN,
		TMax:         req.TMax,
		S0:           s0,
		I0:           i0,
		R0:           r0,
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
	_ = cw.Write([]string{"t", "s", "i", "r"})
	for _, row := range out {
		_ = cw.Write([]string{
			strconv.Itoa(row.T),
			strconv.FormatFloat(row.S, 'f', -1, 64),
			strconv.FormatFloat(row.I, 'f', -1, 64),
			strconv.FormatFloat(row.R, 'f', -1, 64),
		})
	}
}
