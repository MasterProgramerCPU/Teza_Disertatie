package handlers

import (
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

type DatasetsHandler struct {
	datasets       *repository.DatasetRepository
	maxUploadBytes int64
}

func NewDatasetsHandler(datasets *repository.DatasetRepository, maxUpload int64) *DatasetsHandler {
	return &DatasetsHandler{datasets: datasets, maxUploadBytes: maxUpload}
}

func (h *DatasetsHandler) List(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	out, err := h.datasets.ListByStudy(r.Context(), sid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not list datasets")
		return
	}
	if out == nil {
		out = []models.Dataset{}
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *DatasetsHandler) Get(w http.ResponseWriter, r *http.Request) {
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
	d, err := h.datasets.Get(r.Context(), sid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "dataset not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failure")
		return
	}
	writeJSON(w, http.StatusOK, d)
}

func (h *DatasetsHandler) Delete(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())
	role, _ := authmw.StudyRoleFrom(r.Context())

	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}

	// Admin sterge orice. Contributor sterge doar dataseturile proprii.
	var ownerFilter *uuid.UUID
	if role == models.RoleContributor {
		ownerFilter = &uid
	}

	err = h.datasets.Delete(r.Context(), sid, id, ownerFilter)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "dataset not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failure")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *DatasetsHandler) Create(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())

	if err := r.ParseMultipartForm(h.maxUploadBytes); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart: "+err.Error())
		return
	}

	name := strings.TrimSpace(r.FormValue("name"))
	disease := strings.TrimSpace(r.FormValue("disease_code"))
	if name == "" || disease == "" {
		writeError(w, http.StatusBadRequest, "name and disease_code are required")
		return
	}

	file, _, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "file is required")
		return
	}
	defer file.Close()

	records, parseErr := parseCSV(io.LimitReader(file, h.maxUploadBytes))
	if parseErr != nil {
		writeError(w, http.StatusBadRequest, parseErr.Error())
		return
	}
	if len(records) == 0 {
		writeError(w, http.StatusBadRequest, "no records found in CSV")
		return
	}

	d, err := h.datasets.Create(r.Context(), sid, uid, name, disease, records)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not save dataset: "+err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, d)
}

func parseCSV(rd io.Reader) ([]models.EpidemiologicalRecord, error) {
	cr := csv.NewReader(rd)
	cr.TrimLeadingSpace = true
	header, err := cr.Read()
	if err != nil {
		return nil, fmt.Errorf("missing header row: %w", err)
	}
	idx := indexHeader(header)
	if err := requireColumns(idx, "date", "region", "infected", "population"); err != nil {
		return nil, err
	}

	var out []models.EpidemiologicalRecord
	line := 1
	var lastDate time.Time

	for {
		row, err := cr.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("line %d: %w", line+1, err)
		}
		line++

		rec := models.EpidemiologicalRecord{}
		d, err := time.Parse("2006-01-02", strings.TrimSpace(row[idx["date"]]))
		if err != nil {
			return nil, fmt.Errorf("line %d: invalid date: %w", line, err)
		}
		rec.RecordedDate = d
		rec.RegionCode = strings.TrimSpace(row[idx["region"]])
		if rec.RegionCode == "" {
			return nil, fmt.Errorf("line %d: empty region", line)
		}

		rec.Infected, err = parseInt64(row[idx["infected"]])
		if err != nil {
			return nil, fmt.Errorf("line %d: infected: %w", line, err)
		}
		rec.Population, err = parseInt64(row[idx["population"]])
		if err != nil {
			return nil, fmt.Errorf("line %d: population: %w", line, err)
		}
		if rec.Population <= 0 {
			return nil, fmt.Errorf("line %d: population must be > 0", line)
		}

		if i, ok := idx["recovered"]; ok && i < len(row) && row[i] != "" {
			v, err := parseInt64(row[i])
			if err != nil {
				return nil, fmt.Errorf("line %d: recovered: %w", line, err)
			}
			rec.Recovered = &v
		}
		if i, ok := idx["susceptible"]; ok && i < len(row) && row[i] != "" {
			v, err := parseInt64(row[i])
			if err != nil {
				return nil, fmt.Errorf("line %d: susceptible: %w", line, err)
			}
			rec.Susceptible = &v
		}

		// Coloane epi extinse (toate opt). Pentru fiecare, daca header-ul exista
		// si valoarea e non-vida, o parsam. Tipurile int vs float sunt explicite.
		optInt := func(col string) (*int64, error) {
			i, ok := idx[col]
			if !ok || i >= len(row) || row[i] == "" {
				return nil, nil
			}
			v, err := parseInt64(row[i])
			if err != nil {
				return nil, fmt.Errorf("line %d: %s: %w", line, col, err)
			}
			return &v, nil
		}
		optFloat := func(col string) (*float64, error) {
			i, ok := idx[col]
			if !ok || i >= len(row) || row[i] == "" {
				return nil, nil
			}
			v, err := strconv.ParseFloat(strings.TrimSpace(row[i]), 64)
			if err != nil {
				return nil, fmt.Errorf("line %d: %s: %w", line, col, err)
			}
			return &v, nil
		}
		for _, p := range []struct {
			col string
			dst **int64
		}{
			{"deaths", &rec.Deaths},
			{"new_cases", &rec.NewCases},
			{"new_deaths", &rec.NewDeaths},
			{"hospitalized", &rec.Hospitalized},
			{"icu", &rec.ICU},
			{"vaccinated", &rec.Vaccinated},
			{"tested", &rec.Tested},
		} {
			v, err := optInt(p.col)
			if err != nil {
				return nil, err
			}
			*p.dst = v
		}
		for _, p := range []struct {
			col string
			dst **float64
		}{
			{"stringency_index", &rec.StringencyIndex},
			{"reproduction_rate", &rec.ReproductionRate},
		} {
			v, err := optFloat(p.col)
			if err != nil {
				return nil, err
			}
			*p.dst = v
		}

		var rec_ int64
		if rec.Recovered != nil {
			rec_ = *rec.Recovered
		}
		if rec.Infected+rec_ > rec.Population {
			return nil, fmt.Errorf("line %d: I+R exceeds population", line)
		}

		if !lastDate.IsZero() && d.Before(lastDate) {
			return nil, fmt.Errorf("line %d: dates not in chronological order", line)
		}
		lastDate = d

		out = append(out, rec)
	}
	return out, nil
}

func indexHeader(header []string) map[string]int {
	idx := map[string]int{}
	for i, h := range header {
		idx[strings.ToLower(strings.TrimSpace(h))] = i
	}
	return idx
}

func requireColumns(idx map[string]int, cols ...string) error {
	var missing []string
	for _, c := range cols {
		if _, ok := idx[c]; !ok {
			missing = append(missing, c)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("missing required columns: %s", strings.Join(missing, ", "))
	}
	return nil
}

func parseInt64(s string) (int64, error) {
	return strconv.ParseInt(strings.TrimSpace(s), 10, 64)
}
