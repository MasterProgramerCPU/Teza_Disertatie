package handlers

import (
	"errors"
	"log"
	"net/http"

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
