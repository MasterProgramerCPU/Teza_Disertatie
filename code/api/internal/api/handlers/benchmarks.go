package handlers

import (
	"net/http"

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
