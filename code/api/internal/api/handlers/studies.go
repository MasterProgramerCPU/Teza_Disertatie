package handlers

import (
	"errors"
	"log"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

type StudiesHandler struct {
	studies *repository.StudyRepository
	members *repository.StudyMemberRepository
	users   *repository.UserRepository
}

func NewStudiesHandler(studies *repository.StudyRepository, members *repository.StudyMemberRepository, users *repository.UserRepository) *StudiesHandler {
	return &StudiesHandler{studies: studies, members: members, users: users}
}

type studyPayload struct {
	Name        string `json:"name"`
	DiseaseCode string `json:"disease_code"`
	Description string `json:"description"`
}

func (p *studyPayload) normalize() {
	p.Name = strings.TrimSpace(p.Name)
	p.DiseaseCode = strings.TrimSpace(p.DiseaseCode)
	p.Description = strings.TrimSpace(p.Description)
}

func (p *studyPayload) validate() error {
	if p.Name == "" {
		return errors.New("name required")
	}
	if p.DiseaseCode == "" {
		return errors.New("disease_code required")
	}
	return nil
}

// List returneaza studiile in care userul curent e membru. Pentru super admin,
// returneaza toate studiile.
func (h *StudiesHandler) List(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	user, err := h.users.GetByID(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "user lookup failed")
		return
	}

	if user.IsSuperAdmin {
		all, err := h.studies.ListAll(r.Context())
		if err != nil {
			log.Printf("studies.List super: %v", err)
			writeError(w, http.StatusInternalServerError, "list failed")
			return
		}
		writeJSON(w, http.StatusOK, all)
		return
	}

	mine, err := h.studies.ListForUser(r.Context(), uid)
	if err != nil {
		log.Printf("studies.List user: %v", err)
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, mine)
}

// Create creeaza un studiu nou. Userul care l-a creat devine automat admin.
// Super-adminii pot crea studii pentru altii (TODO: implementat ulterior).
func (h *StudiesHandler) Create(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}

	var p studyPayload
	if err := decodeJSON(r, &p); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	p.normalize()
	if err := p.validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	study, err := h.studies.Create(r.Context(), p.Name, p.DiseaseCode, p.Description, uid)
	if err != nil {
		log.Printf("studies.Create: %v", err)
		writeError(w, http.StatusInternalServerError, "could not create study")
		return
	}

	// Creatorul devine admin automat in studiul nou-creat.
	if _, err := h.members.Add(r.Context(), study.ID, uid, models.RoleAdmin); err != nil {
		log.Printf("studies.Create: members.Add admin failed: %v", err)
		// nu rollback explicit — clusterul YugabyteDB e tranzactional la nivel de query
		writeError(w, http.StatusInternalServerError, "study created but admin assignment failed")
		return
	}

	writeJSON(w, http.StatusCreated, study)
}

// Get returneaza un studiu. Membership-ul este deja verificat de middleware.
func (h *StudiesHandler) Get(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	study, err := h.studies.GetByID(r.Context(), sid)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "study not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "study lookup failed")
		return
	}
	writeJSON(w, http.StatusOK, study)
}

// Update modifica metadata studiului. Doar admin.
func (h *StudiesHandler) Update(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}

	var p studyPayload
	if err := decodeJSON(r, &p); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	p.normalize()
	if err := p.validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	study, err := h.studies.Update(r.Context(), sid, p.Name, p.DiseaseCode, p.Description)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "study not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	writeJSON(w, http.StatusOK, study)
}

// Delete sterge un studiu (cu cascade pe membri si pe dataset-uri/simulari). Doar admin.
func (h *StudiesHandler) Delete(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	if err := h.studies.Delete(r.Context(), sid); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "study not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ListMembers returneaza membrii unui studiu.
func (h *StudiesHandler) ListMembers(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	out, err := h.members.ListForStudy(r.Context(), sid)
	if err != nil {
		log.Printf("members.ListForStudy: %v", err)
		writeError(w, http.StatusInternalServerError, "list members failed")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

type addMemberPayload struct {
	Email string `json:"email"`
	Role  string `json:"role"`
}

func (h *StudiesHandler) AddMember(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}

	var p addMemberPayload
	if err := decodeJSON(r, &p); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	p.Email = strings.ToLower(strings.TrimSpace(p.Email))
	if p.Email == "" || !models.ValidStudyRole(p.Role) {
		writeError(w, http.StatusBadRequest, "email and valid role required")
		return
	}

	user, err := h.users.GetByEmail(r.Context(), p.Email)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "user not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "user lookup failed")
		return
	}

	m, err := h.members.Add(r.Context(), sid, user.ID, models.StudyRole(p.Role))
	if errors.Is(err, repository.ErrDuplicate) {
		writeError(w, http.StatusConflict, "user already member")
		return
	}
	if err != nil {
		log.Printf("members.Add: %v", err)
		writeError(w, http.StatusInternalServerError, "add member failed")
		return
	}
	m.Email = user.Email
	writeJSON(w, http.StatusCreated, m)
}

type updateRolePayload struct {
	Role string `json:"role"`
}

func (h *StudiesHandler) UpdateMemberRole(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uidStr := chi.URLParam(r, "userId")
	uid, err := uuid.Parse(uidStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid userId")
		return
	}

	var p updateRolePayload
	if err := decodeJSON(r, &p); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if !models.ValidStudyRole(p.Role) {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}

	if err := h.members.UpdateRole(r.Context(), sid, uid, models.StudyRole(p.Role)); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "membership not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "update role failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *StudiesHandler) RemoveMember(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uidStr := chi.URLParam(r, "userId")
	uid, err := uuid.Parse(uidStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid userId")
		return
	}
	if err := h.members.Remove(r.Context(), sid, uid); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "membership not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "remove member failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
