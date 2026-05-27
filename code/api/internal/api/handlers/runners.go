package handlers

import (
	"context"
	"errors"
	"log"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/k8s"
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
	k8s     *k8s.Manager
}

func NewRunnersHandler(runners *repository.RunnerRepository, mgr *k8s.Manager) *RunnersHandler {
	return &RunnersHandler{runners: runners, k8s: mgr}
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

	// Provisioning K8s: cream Deployment-ul asincron, ca raspunsul HTTP sa fie
	// rapid. Statusul incepe `building` si wrapper-ul din pod il muta la `ready`
	// dupa ce isi incarca scriptul si se conecteaza la Redis.
	if h.k8s.Enabled() {
		out.Status = models.RunnerStatusBuilding
		out.DeploymentName = k8s.DeploymentName(out.ID)
		if err := h.runners.UpdateStatus(r.Context(), out.ID,
			models.RunnerStatusBuilding, "", "", out.DeploymentName); err != nil {
			log.Printf("runner %s: could not pre-set building status: %v", out.ID, err)
		}
		go h.provisionDeployment(out.ID, out.Name)
	} else {
		// In modul dev fara cluster, marcam direct ready: scriptul ramane
		// inregistrat dar nu se executa decat daca un runner-custom e pornit manual.
		_ = h.runners.UpdateStatus(r.Context(), out.ID,
			models.RunnerStatusReady, "dev mode (no k8s provisioning)", "", "")
		out.Status = models.RunnerStatusReady
	}
	writeJSON(w, http.StatusCreated, out)
}

// provisionDeployment creeaza Deployment-ul K8s in fundal. Daca esueaza,
// muta runner-ul in starea `failed` cu mesajul de eroare.
func (h *RunnersHandler) provisionDeployment(id uuid.UUID, name string) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	depName, err := h.k8s.CreateRunnerDeployment(ctx, id, name)
	if err != nil {
		log.Printf("runner %s provisioning failed: %v", id, err)
		_ = h.runners.UpdateStatus(ctx, id, models.RunnerStatusFailed, err.Error(), "", "")
		return
	}
	// Lasam wrapper-ul din pod sa mute statusul la `ready` dupa ce reuseste
	// sa se conecteze; aici doar inregistram numele Deployment-ului.
	if err := h.runners.UpdateStatus(ctx, id, models.RunnerStatusBuilding,
		"deployment created", "", depName); err != nil {
		log.Printf("runner %s: could not record deployment name: %v", id, err)
	}
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

// Delete sterge inregistrarea runner-ului din DB si Deployment-ul K8s asociat.
// Doar super-adminul poate apela (impus prin middleware in router). Ordinea:
// citim mai intai numele Deployment-ului, stergem K8s (idempotent), apoi DB.
// Daca stergerea K8s esueaza, NU stergem din DB --- ramane vizibil ca `failed`.
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

	rn, err := h.runners.Get(r.Context(), sid, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "runner not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failure")
		return
	}

	if err := h.k8s.DeleteRunnerDeployment(r.Context(), rn.DeploymentName); err != nil {
		_ = h.runners.UpdateStatus(r.Context(), id, models.RunnerStatusFailed,
			"k8s delete: "+err.Error(), "", "")
		writeError(w, http.StatusInternalServerError, "k8s delete failed: "+err.Error())
		return
	}

	if err := h.runners.Delete(r.Context(), sid, id); err != nil {
		writeError(w, http.StatusInternalServerError, "delete failure")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}
