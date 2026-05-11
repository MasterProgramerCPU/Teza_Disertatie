package handlers

import (
	"net/http"

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
	out, err := h.benches.AggregateByModelAndLanguage(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "aggregate query failure: "+err.Error())
		return
	}
	if out == nil {
		out = []models.BenchmarkAggregate{}
	}
	writeJSON(w, http.StatusOK, out)
}
