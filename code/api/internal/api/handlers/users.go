package handlers

import (
	"log"
	"net/http"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
)

// UsersHandler expune endpoint-uri legate de profilul userului curent.
type UsersHandler struct {
	users   *repository.UserRepository
	studies *repository.StudyRepository
}

func NewUsersHandler(users *repository.UserRepository, studies *repository.StudyRepository) *UsersHandler {
	return &UsersHandler{users: users, studies: studies}
}

// Me returneaza userul curent + studiile in care e membru, cu rolul in fiecare.
// Pentru super admin, e returnata si lista completa de studii.
func (h *UsersHandler) Me(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	user, err := h.users.GetByID(r.Context(), uid)
	if err != nil {
		log.Printf("me: users.GetByID error: %v", err)
		writeError(w, http.StatusInternalServerError, "user lookup failed")
		return
	}

	memberships, err := h.studies.ListForUser(r.Context(), uid)
	if err != nil {
		log.Printf("me: studies.ListForUser error: %v", err)
		writeError(w, http.StatusInternalServerError, "studies lookup failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"id":             user.ID,
		"email":          user.Email,
		"is_super_admin": user.IsSuperAdmin,
		"created_at":     user.CreatedAt,
		"studies":        memberships,
	})
}
