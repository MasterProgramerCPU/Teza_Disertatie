package handlers

import (
	"errors"
	"net/http"
	"regexp"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

// maxScriptBytes plafoneaza dimensiunea scriptului user upload-at. Scripturile
// de cercetare obisnuite sunt sub 100 KB; un plafon mai mare ar permite atacuri
// triviale de epuizare a stocarii sau a memoriei la parsare.
const maxScriptBytes = 1 << 20 // 1 MB

// validRunnerName limiteaza numele runner-ului la caractere sigure pentru a fi
// folosite ulterior in numele cozii Redis si al deployment-ului Kubernetes.
var validRunnerName = regexp.MustCompile(`^[a-z][a-z0-9-]{1,62}[a-z0-9]$`)

type RunnersHandler struct {
	runners *repository.RunnerRepository
}

func NewRunnersHandler(runners *repository.RunnerRepository) *RunnersHandler {
	return &RunnersHandler{runners: runners}
}

type createRunnerReq struct {
	Name            string         `json:"name"`
	Description     string         `json:"description"`
	ScriptContent   string         `json:"script_content"`
	ParameterSchema map[string]any `json:"parameter_schema"`
}

// Create inregistreaza un runner nou intr-un studiu. Conform politicii de
// plug-in-uri, doar super-adminul poate crea (vezi router). Runner-ul ramane in
// starea `pending` pana cand pipeline-ul de build (faza ulterioara) il preia.
func (h *RunnersHandler) Create(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	uid, _ := authmw.UserIDFrom(r.Context())

	var req createRunnerReq
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	req.Name = strings.TrimSpace(strings.ToLower(req.Name))
	if !validRunnerName.MatchString(req.Name) {
		writeError(w, http.StatusBadRequest,
			"name must match ^[a-z][a-z0-9-]{1,62}[a-z0-9]$ (DNS-safe label)")
		return
	}
	if strings.TrimSpace(req.ScriptContent) == "" {
		writeError(w, http.StatusBadRequest, "script_content required")
		return
	}
	if len(req.ScriptContent) > maxScriptBytes {
		writeError(w, http.StatusBadRequest, "script exceeds maximum size of 1 MB")
		return
	}
	if req.ParameterSchema == nil {
		req.ParameterSchema = map[string]any{}
	}

	// Numele cozii Redis si al deployment-ului K8s deriva din runner-id, pentru
	// a fi unice global in cluster si independente de numele uman ales de user.
	// Le populam dupa Create (avem ID-ul), prin UpdateStatus.
	queueName := "epimodel:jobs:custom-" + req.Name

	out, err := h.runners.Create(r.Context(), sid, uid,
		req.Name, req.Description, req.ScriptContent, req.ParameterSchema, queueName)
	if errors.Is(err, repository.ErrDuplicate) {
		writeError(w, http.StatusConflict, "runner with this name already exists in study")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not create runner: "+err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, out)
}

// List intoarce runner-ele scope-uite la studiu, vizibile oricarui membru.
// Scriptul nu este returnat aici, doar metadatele; vezi Get pentru continut.
func (h *RunnersHandler) List(w http.ResponseWriter, r *http.Request) {
	sid, ok := authmw.StudyIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusBadRequest, "missing study context")
		return
	}
	out, err := h.runners.ListByStudy(r.Context(), sid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not list runners")
		return
	}
	for i := range out {
		out[i].ScriptContent = "" // metadate-only in listare
	}
	if out == nil {
		out = []models.Runner{}
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *RunnersHandler) Get(w http.ResponseWriter, r *http.Request) {
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
	rn, err := h.runners.Get(r.Context(), sid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "runner not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failure")
		return
	}
	writeJSON(w, http.StatusOK, rn)
}

// Delete sterge inregistrarea runner-ului din DB. In fazele ulterioare, aceasta
// va declansa si scale-to-zero pe Deployment-ul K8s asociat (vezi router).
// Doar super-adminul poate apela (impus prin middleware in router).
func (h *RunnersHandler) Delete(w http.ResponseWriter, r *http.Request) {
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
	err = h.runners.Delete(r.Context(), sid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "runner not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failure")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}
