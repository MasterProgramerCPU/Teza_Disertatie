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

// validRunnerName limiteaza numele runner-ului la caractere sigure pentru a fi
// folosite ulterior in numele cozii Redis si al deployment-ului Kubernetes.
var validRunnerName = regexp.MustCompile(`^[a-z][a-z0-9-]{1,62}[a-z0-9]$`)

// validImageRef face o verificare de sanitate pe referinta de imagine; nu
// reimplementam parser-ul OCI complet, doar respingem inputuri evident gresite
// (spatii, caractere de control, lungime). K8s va respinge si el referintele
// realmente invalide la momentul pull-ului.
var validImageRef = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9._/:@-]{1,254}$`)

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
	Image           string         `json:"image"`
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
	req.Image = strings.TrimSpace(req.Image)
	if !validRunnerName.MatchString(req.Name) {
		writeError(w, http.StatusBadRequest,
			"name must match ^[a-z][a-z0-9-]{1,62}[a-z0-9]$ (DNS-safe label)")
		return
	}
	if req.Image == "" {
		writeError(w, http.StatusBadRequest, "image required")
		return
	}
	if !validImageRef.MatchString(req.Image) {
		writeError(w, http.StatusBadRequest,
			"image must be a valid container image reference")
		return
	}
	if req.ParameterSchema == nil {
		req.ParameterSchema = map[string]any{}
	}

	// Numele cozii Redis deriva din numele runner-ului, garantat DNS-safe prin
	// validarea de mai sus. Pasat ca env var RUNNER_QUEUE la container.
	queueName := "epimodel:jobs:custom-" + req.Name

	out, err := h.runners.Create(r.Context(), sid, uid,
		req.Name, req.Description, req.Image, req.ParameterSchema, queueName)
	if errors.Is(err, repository.ErrDuplicate) {
		writeError(w, http.StatusConflict, "runner with this name already exists in study")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not create runner: "+err.Error())
		return
	}

	// Provisioning K8s asincron: raspunsul HTTP intoarce rapid, iar Deployment-ul
	// se creeaza in fundal. Statusul incepe `building` si trece la `ready` cand
	// Deployment-ul a fost creat cu succes (imaginea user-ului e responsabila de
	// propria pornire si conectare la coada Redis).
	if h.k8s.Enabled() {
		out.Status = models.RunnerStatusBuilding
		out.DeploymentName = k8s.DeploymentName(out.ID)
		if err := h.runners.UpdateStatus(r.Context(), out.ID,
			models.RunnerStatusBuilding, "", out.DeploymentName); err != nil {
			log.Printf("runner %s: could not pre-set building status: %v", out.ID, err)
		}
		go h.provisionDeployment(out.ID, out.Name, out.QueueName, out.Image)
	} else {
		_ = h.runners.UpdateStatus(r.Context(), out.ID,
			models.RunnerStatusReady, "dev mode (no k8s provisioning)", "")
		out.Status = models.RunnerStatusReady
	}
	writeJSON(w, http.StatusCreated, out)
}

// provisionDeployment creeaza Deployment-ul K8s in fundal pentru un runner
// bazat pe imagine externa. Marcheaza ready imediat dupa creare; daca esueaza,
// muta runner-ul in starea failed cu mesajul de eroare.
func (h *RunnersHandler) provisionDeployment(id uuid.UUID, name, queueName, image string) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	depName, err := h.k8s.CreateRunnerDeployment(ctx, id, name, queueName, image)
	if err != nil {
		log.Printf("runner %s provisioning failed: %v", id, err)
		_ = h.runners.UpdateStatus(ctx, id, models.RunnerStatusFailed, err.Error(), "")
		return
	}
	if err := h.runners.UpdateStatus(ctx, id, models.RunnerStatusReady,
		"deployment created", depName); err != nil {
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
			"k8s delete: "+err.Error(), "")
		writeError(w, http.StatusInternalServerError, "k8s delete failed: "+err.Error())
		return
	}

	if err := h.runners.Delete(r.Context(), sid, id); err != nil {
		writeError(w, http.StatusInternalServerError, "delete failure")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}
