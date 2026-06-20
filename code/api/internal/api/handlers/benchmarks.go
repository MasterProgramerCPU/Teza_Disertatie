package handlers

import (
	"net/http"

	"github.com/go-chi/chi/v5"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

type BenchmarksHandler struct {
	benches *repository.BenchmarkRepository
}

func NewBenchmarksHandler(benches *repository.BenchmarkRepository) *BenchmarksHandler {
	return &BenchmarksHandler{benches: benches}
}

func (h *BenchmarksHandler) Aggregate(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	out, err := h.benches.AggregateByModelAndLanguage(r.Context(), sid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "aggregate query failure: "+err.Error())
		return
	}
	if out == nil {
		out = []models.BenchmarkAggregate{}
	}
	writeJSON(w, http.StatusOK, out)
}

// validModelTypes / validLanguages: liste albe pentru parametrii din URL ai
// endpoint-ului de detaliu. Echivalente cu CHECK-urile din schema DB.
var (
	validModelTypes = map[string]struct{}{
		"sis": {}, "sir": {}, "seir": {}, "sirs": {},
		"sidarthe": {}, "lstm": {}, "script": {},
	}
	validLanguages = map[string]struct{}{
		"r": {}, "julia": {}, "python": {},
	}
)

// RunsForCombination expune rularile individuale care formeaza un agregat
// (model x limbaj) — folosit de pagina de detaliu a benchmark-ului.
func (h *BenchmarksHandler) RunsForCombination(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	model := chi.URLParam(r, "model")
	lang := chi.URLParam(r, "language")
	if _, ok := validModelTypes[model]; !ok {
		writeError(w, http.StatusBadRequest, "invalid model_type")
		return
	}
	if _, ok := validLanguages[lang]; !ok {
		writeError(w, http.StatusBadRequest, "invalid language")
		return
	}
	out, err := h.benches.ListRunsForModelLanguage(r.Context(), sid, model, lang)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "runs query failure: "+err.Error())
		return
	}
	if out == nil {
		out = []models.BenchmarkRun{}
	}
	writeJSON(w, http.StatusOK, out)
}
