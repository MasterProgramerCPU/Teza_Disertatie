package middleware

import (
	"context"
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

const (
	studyIDKey   ctxKey = "study_id"
	studyRoleKey ctxKey = "study_role"
)

// RBAC contine dependentele necesare pentru middleware-urile de autorizare.
type RBAC struct {
	Users        *repository.UserRepository
	StudyMembers *repository.StudyMemberRepository
}

func NewRBAC(users *repository.UserRepository, members *repository.StudyMemberRepository) *RBAC {
	return &RBAC{Users: users, StudyMembers: members}
}

// RequireSuperAdmin permite trecerea doar daca userul curent are is_super_admin=true.
func (rb *RBAC) RequireSuperAdmin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		uid, ok := UserIDFrom(r.Context())
		if !ok {
			writeAuthError(w, "missing user context")
			return
		}
		user, err := rb.Users.GetByID(r.Context(), uid)
		if err != nil || user == nil {
			writeAuthError(w, "user lookup failed")
			return
		}
		if !user.IsSuperAdmin {
			writeForbidden(w, "super admin required")
			return
		}
		next.ServeHTTP(w, r)
	})
}

// RequireStudyMembership verifica daca userul are unul din rolurile permise in studiul
// identificat de URL param "studyId". Super-adminul trece intotdeauna.
// Daca allowedRoles e gol, orice rol valid trece (doar membership-ul conteaza).
func (rb *RBAC) RequireStudyMembership(allowedRoles ...models.StudyRole) func(http.Handler) http.Handler {
	allowed := make(map[models.StudyRole]struct{}, len(allowedRoles))
	for _, r := range allowedRoles {
		allowed[r] = struct{}{}
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			uid, ok := UserIDFrom(r.Context())
			if !ok {
				writeAuthError(w, "missing user context")
				return
			}

			studyIDStr := chi.URLParam(r, "studyId")
			studyID, err := uuid.Parse(studyIDStr)
			if err != nil {
				writeBadRequest(w, "invalid studyId")
				return
			}

			// Super-adminul are acces direct, fara verificare de membership.
			user, err := rb.Users.GetByID(r.Context(), uid)
			if err != nil {
				writeAuthError(w, "user lookup failed")
				return
			}

			ctx := context.WithValue(r.Context(), studyIDKey, studyID)

			if user.IsSuperAdmin {
				ctx = context.WithValue(ctx, studyRoleKey, models.RoleAdmin)
				next.ServeHTTP(w, r.WithContext(ctx))
				return
			}

			role, err := rb.StudyMembers.GetRole(r.Context(), studyID, uid)
			if errors.Is(err, repository.ErrNotFound) {
				writeForbidden(w, "not a member of this study")
				return
			}
			if err != nil {
				writeForbidden(w, "membership lookup failed")
				return
			}

			if len(allowed) > 0 {
				if _, ok := allowed[role]; !ok {
					writeForbidden(w, "insufficient role")
					return
				}
			}

			ctx = context.WithValue(ctx, studyRoleKey, role)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// StudyIDFrom returneaza ID-ul studiului curent din context.
func StudyIDFrom(ctx context.Context) (uuid.UUID, bool) {
	v := ctx.Value(studyIDKey)
	id, ok := v.(uuid.UUID)
	return id, ok
}

// StudyRoleFrom returneaza rolul userului curent in studiul din context.
func StudyRoleFrom(ctx context.Context) (models.StudyRole, bool) {
	v := ctx.Value(studyRoleKey)
	r, ok := v.(models.StudyRole)
	return r, ok
}

func writeForbidden(w http.ResponseWriter, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusForbidden)
	_, _ = w.Write([]byte(`{"error":{"code":403,"message":"` + msg + `"}}`))
}

func writeBadRequest(w http.ResponseWriter, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusBadRequest)
	_, _ = w.Write([]byte(`{"error":{"code":400,"message":"` + msg + `"}}`))
}
