package handlers

import (
	"context"
	"errors"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/db/repository"
)

// AdminHandler expune endpoint-uri vizibile doar super-adminilor.
type AdminHandler struct {
	users   *repository.UserRepository
	studies *repository.StudyRepository
	pool    *pgxpool.Pool
}

func NewAdminHandler(users *repository.UserRepository, studies *repository.StudyRepository, pool *pgxpool.Pool) *AdminHandler {
	return &AdminHandler{users: users, studies: studies, pool: pool}
}

func (h *AdminHandler) ListUsers(w http.ResponseWriter, r *http.Request) {
	all, err := h.users.ListAll(r.Context())
	if err != nil {
		log.Printf("admin.ListUsers: %v", err)
		writeError(w, http.StatusInternalServerError, "list users failed")
		return
	}
	writeJSON(w, http.StatusOK, all)
}

type setSuperAdminPayload struct {
	IsSuperAdmin bool `json:"is_super_admin"`
}

func (h *AdminHandler) SetSuperAdmin(w http.ResponseWriter, r *http.Request) {
	uidStr := chi.URLParam(r, "userId")
	uid, err := uuid.Parse(uidStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid userId")
		return
	}

	var p setSuperAdminPayload
	if err := decodeJSON(r, &p); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}

	if err := h.users.SetSuperAdmin(r.Context(), uid, p.IsSuperAdmin); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ListStudies returneaza toate studiile din sistem (super admin only).
func (h *AdminHandler) ListStudies(w http.ResponseWriter, r *http.Request) {
	all, err := h.studies.ListAll(r.Context())
	if err != nil {
		log.Printf("admin.ListStudies: %v", err)
		writeError(w, http.StatusInternalServerError, "list studies failed")
		return
	}
	writeJSON(w, http.StatusOK, all)
}

// Stats returneaza contoare globale pentru UI-ul admin.
func (h *AdminHandler) Stats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	users, err := h.users.CountAll(ctx)
	if err != nil {
		log.Printf("admin.Stats users: %v", err)
		writeError(w, http.StatusInternalServerError, "stats failed")
		return
	}
	supers, err := h.users.CountSuperAdmins(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "stats failed")
		return
	}
	studies, err := h.studies.CountAll(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "stats failed")
		return
	}

	type rowCount struct {
		dest *int
		sql  string
	}
	datasets, records, sims, completed, benches := 0, 0, 0, 0, 0
	queries := []rowCount{
		{&datasets, "SELECT COUNT(*) FROM datasets"},
		{&records, "SELECT COUNT(*) FROM epidemiological_records"},
		{&sims, "SELECT COUNT(*) FROM simulation_runs"},
		{&completed, "SELECT COUNT(*) FROM simulation_runs WHERE status='completed'"},
		{&benches, "SELECT COUNT(*) FROM benchmarks"},
	}
	for _, q := range queries {
		if err := h.pool.QueryRow(ctx, q.sql).Scan(q.dest); err != nil {
			log.Printf("admin.Stats %q: %v", q.sql, err)
			writeError(w, http.StatusInternalServerError, "stats failed")
			return
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"users":                 users,
		"super_admins":          supers,
		"studies":               studies,
		"datasets":              datasets,
		"epi_records":           records,
		"simulations":           sims,
		"simulations_completed": completed,
		"benchmarks":            benches,
	})
}

type labeledCount struct {
	Label string `json:"label"`
	Count int    `json:"count"`
}

type studyVolume struct {
	StudyID     uuid.UUID `json:"study_id"`
	Name        string    `json:"name"`
	RecordCount int64     `json:"record_count"`
}

func (h *AdminHandler) groupCounts(ctx context.Context, sql string) ([]labeledCount, error) {
	rows, err := h.pool.Query(ctx, sql)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []labeledCount{}
	for rows.Next() {
		var lc labeledCount
		if err := rows.Scan(&lc.Label, &lc.Count); err != nil {
			return nil, err
		}
		out = append(out, lc)
	}
	return out, rows.Err()
}

// Breakdown returneaza distributii agregate cross-studiu pentru dashboard:
// simulari pe status / model / limbaj, dataseturi si studii pe boala, top
// studii dupa volumul de inregistrari.
func (h *AdminHandler) Breakdown(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	type bucket struct {
		out *[]labeledCount
		sql string
	}
	var byStatus, byModel, byLanguage, datasetsByDisease, studiesByDisease []labeledCount
	queries := []bucket{
		{&byStatus, `SELECT status,       COUNT(*) FROM simulation_runs GROUP BY status       ORDER BY status`},
		{&byModel, `SELECT model_type,   COUNT(*) FROM simulation_runs GROUP BY model_type   ORDER BY model_type`},
		{&byLanguage, `SELECT language,     COUNT(*) FROM simulation_runs GROUP BY language     ORDER BY language`},
		{&datasetsByDisease, `SELECT disease_code, COUNT(*) FROM datasets        GROUP BY disease_code ORDER BY disease_code`},
		{&studiesByDisease, `SELECT disease_code, COUNT(*) FROM studies         GROUP BY disease_code ORDER BY disease_code`},
	}
	for _, q := range queries {
		rows, err := h.groupCounts(ctx, q.sql)
		if err != nil {
			log.Printf("admin.Breakdown: %v", err)
			writeError(w, http.StatusInternalServerError, "breakdown failed")
			return
		}
		*q.out = rows
	}

	topRows, err := h.pool.Query(ctx, `
		SELECT s.id, s.name, COALESCE(SUM(d.record_count), 0)::bigint
		FROM studies s
		LEFT JOIN datasets d ON d.study_id = s.id
		GROUP BY s.id, s.name
		ORDER BY 3 DESC
		LIMIT 10`)
	if err != nil {
		log.Printf("admin.Breakdown top: %v", err)
		writeError(w, http.StatusInternalServerError, "breakdown failed")
		return
	}
	defer topRows.Close()
	top := []studyVolume{}
	for topRows.Next() {
		var sv studyVolume
		if err := topRows.Scan(&sv.StudyID, &sv.Name, &sv.RecordCount); err != nil {
			writeError(w, http.StatusInternalServerError, "breakdown failed")
			return
		}
		top = append(top, sv)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"simulations_by_status":   byStatus,
		"simulations_by_model":    byModel,
		"simulations_by_language": byLanguage,
		"datasets_by_disease":     datasetsByDisease,
		"studies_by_disease":      studiesByDisease,
		"top_studies_by_records":  top,
	})
}

func parseLimit(r *http.Request, def, maxLimit int) int {
	v := r.URL.Query().Get("limit")
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 1 {
		return def
	}
	if n > maxLimit {
		return maxLimit
	}
	return n
}

type recentSimulation struct {
	ID          uuid.UUID  `json:"id"`
	StudyID     uuid.UUID  `json:"study_id"`
	StudyName   string     `json:"study_name"`
	UserEmail   string     `json:"user_email"`
	ModelType   string     `json:"model_type"`
	Language    string     `json:"language"`
	Status      string     `json:"status"`
	TMax        int        `json:"t_max"`
	CreatedAt   time.Time  `json:"created_at"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
}

// RecentSimulations returneaza ultimele N simulari, cross-studiu, cu numele
// studiului si emailul utilizatorului care le-a lansat. Implicit 20, max 200.
func (h *AdminHandler) RecentSimulations(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r, 20, 200)
	rows, err := h.pool.Query(r.Context(), `
		SELECT s.id, s.study_id, st.name, u.email, s.model_type, s.language,
		       s.status, s.t_max, s.created_at, s.completed_at
		FROM simulation_runs s
		JOIN studies st ON st.id = s.study_id
		JOIN users u ON u.id = s.user_id
		ORDER BY s.created_at DESC
		LIMIT $1`, limit)
	if err != nil {
		log.Printf("admin.RecentSimulations: %v", err)
		writeError(w, http.StatusInternalServerError, "recent simulations failed")
		return
	}
	defer rows.Close()
	out := []recentSimulation{}
	for rows.Next() {
		var i recentSimulation
		if err := rows.Scan(&i.ID, &i.StudyID, &i.StudyName, &i.UserEmail,
			&i.ModelType, &i.Language, &i.Status, &i.TMax,
			&i.CreatedAt, &i.CompletedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "recent simulations failed")
			return
		}
		out = append(out, i)
	}
	writeJSON(w, http.StatusOK, out)
}

type recentDataset struct {
	ID          uuid.UUID `json:"id"`
	StudyID     uuid.UUID `json:"study_id"`
	StudyName   string    `json:"study_name"`
	UserEmail   string    `json:"user_email"`
	Name        string    `json:"name"`
	DiseaseCode string    `json:"disease_code"`
	RecordCount int       `json:"record_count"`
	UploadedAt  time.Time `json:"uploaded_at"`
}

// RecentDatasets returneaza ultimele N seturi de date incarcate, cross-studiu.
func (h *AdminHandler) RecentDatasets(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r, 20, 200)
	rows, err := h.pool.Query(r.Context(), `
		SELECT d.id, d.study_id, st.name, u.email, d.name, d.disease_code,
		       d.record_count, d.uploaded_at
		FROM datasets d
		JOIN studies st ON st.id = d.study_id
		JOIN users u ON u.id = d.user_id
		ORDER BY d.uploaded_at DESC
		LIMIT $1`, limit)
	if err != nil {
		log.Printf("admin.RecentDatasets: %v", err)
		writeError(w, http.StatusInternalServerError, "recent datasets failed")
		return
	}
	defer rows.Close()
	out := []recentDataset{}
	for rows.Next() {
		var i recentDataset
		if err := rows.Scan(&i.ID, &i.StudyID, &i.StudyName, &i.UserEmail,
			&i.Name, &i.DiseaseCode, &i.RecordCount, &i.UploadedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "recent datasets failed")
			return
		}
		out = append(out, i)
	}
	writeJSON(w, http.StatusOK, out)
}
