package handlers

import (
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

const maxDraftScriptBytes = 1 << 20 // 1 MB; aceeasi limita ca pentru executie

type ScriptDraftsHandler struct {
	drafts *repository.ScriptDraftRepository
}

func NewScriptDraftsHandler(d *repository.ScriptDraftRepository) *ScriptDraftsHandler {
	return &ScriptDraftsHandler{drafts: d}
}

type scriptDraftReq struct {
	Name           string         `json:"name"`
	Description    string         `json:"description"`
	ScriptContent  string         `json:"script_content"`
	ParametersJSON map[string]any `json:"parameters_json"`
}

func (req *scriptDraftReq) validate() (string, bool) {
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" || len(req.Name) > 128 {
		return "name required (1..128 chars)", false
	}
	if strings.TrimSpace(req.ScriptContent) == "" {
		return "script_content required", false
	}
	if len(req.ScriptContent) > maxDraftScriptBytes {
		return "script_content exceeds maximum size of 1 MB", false
	}
	if req.ParametersJSON == nil {
		req.ParametersJSON = map[string]any{}
	}
	return "", true
}

// Create salveaza un draft nou pentru utilizatorul curent in studiul curent.
func (h *ScriptDraftsHandler) Create(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())

	var req scriptDraftReq
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if msg, ok := req.validate(); !ok {
		writeError(w, http.StatusBadRequest, msg)
		return
	}

	out, err := h.drafts.Create(r.Context(), uid, sid,
		req.Name, req.Description, req.ScriptContent, req.ParametersJSON)
	if errors.Is(err, repository.ErrDuplicate) {
		writeError(w, http.StatusConflict, "draft with this name already exists")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not create draft: "+err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, out)
}

// List intoarce metadatele draft-urilor utilizatorului curent in studiul curent
// (continutul scriptului este omis aici; vezi Get pentru deschiderea unui draft).
func (h *ScriptDraftsHandler) List(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())
	out, err := h.drafts.ListByUserStudy(r.Context(), uid, sid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not list drafts")
		return
	}
	if out == nil {
		out = []models.ScriptDraft{}
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *ScriptDraftsHandler) Get(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	d, err := h.drafts.Get(r.Context(), uid, sid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failure")
		return
	}
	writeJSON(w, http.StatusOK, d)
}

func (h *ScriptDraftsHandler) Update(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}

	var req scriptDraftReq
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if msg, ok := req.validate(); !ok {
		writeError(w, http.StatusBadRequest, msg)
		return
	}

	out, err := h.drafts.Update(r.Context(), uid, sid, id,
		req.Name, req.Description, req.ScriptContent, req.ParametersJSON)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "draft not found")
		return
	}
	if errors.Is(err, repository.ErrDuplicate) {
		writeError(w, http.StatusConflict, "draft with this name already exists")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not update draft: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *ScriptDraftsHandler) Delete(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	err = h.drafts.Delete(r.Context(), uid, sid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failure")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}
