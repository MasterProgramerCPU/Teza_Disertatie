package handlers

import (
	"encoding/base64"
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

// Limite pentru avatar. 256KB e suficient pentru o poza patrata 256x256 JPEG;
// frontend-ul face resize+compresie inainte de upload.
const (
	maxAvatarBytes = 256 * 1024
)

// UsersHandler expune endpoint-uri legate de profilul userului curent si al
// altor cercetatori cu care imparte studii.
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
	profile, err := h.users.GetProfile(r.Context(), uid)
	if err != nil {
		log.Printf("me: users.GetProfile error: %v", err)
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
		"id":             profile.ID,
		"email":          profile.Email,
		"full_name":      profile.FullName,
		"affiliation":    profile.Affiliation,
		"bio":            profile.Bio,
		"has_avatar":     profile.HasAvatar,
		"is_super_admin": profile.IsSuperAdmin,
		"created_at":     profile.CreatedAt,
		"studies":        memberships,
	})
}

// MyProfile returneaza doar campurile de profil ale userului curent.
func (h *UsersHandler) MyProfile(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	profile, err := h.users.GetProfile(r.Context(), uid)
	if err != nil {
		log.Printf("my profile: GetProfile error: %v", err)
		writeError(w, http.StatusInternalServerError, "profile lookup failed")
		return
	}
	writeJSON(w, http.StatusOK, profile)
}

// UpdateMyProfile aplica patch pe campurile editabile ale userului curent.
func (h *UsersHandler) UpdateMyProfile(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	var in models.UserProfileUpdate
	if err := decodeJSON(r, &in); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if err := validateProfileUpdate(&in); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.users.UpdateProfile(r.Context(), uid, in); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		log.Printf("update profile: %v", err)
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	profile, err := h.users.GetProfile(r.Context(), uid)
	if err != nil {
		log.Printf("update profile: re-read: %v", err)
		writeError(w, http.StatusInternalServerError, "profile reload failed")
		return
	}
	writeJSON(w, http.StatusOK, profile)
}

// avatarRequest este corpul JSON acceptat de PUT /api/me/avatar.
// data_base64 este imaginea codificata, cu sau fara prefix data URI.
type avatarRequest struct {
	DataBase64 string `json:"data_base64"`
	MimeType   string `json:"mime_type"`
}

// SetMyAvatar inlocuieste avatarul userului curent.
// Frontend-ul trimite JSON cu imaginea ca base64 (resize+compress facut acolo).
func (h *UsersHandler) SetMyAvatar(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	var in avatarRequest
	if err := decodeJSON(r, &in); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	mime := strings.ToLower(strings.TrimSpace(in.MimeType))
	if mime != "image/jpeg" && mime != "image/png" && mime != "image/webp" {
		writeError(w, http.StatusBadRequest, "unsupported mime type; use image/jpeg, image/png sau image/webp")
		return
	}
	// Acceptam si data URI: "data:image/jpeg;base64,...."
	raw := in.DataBase64
	if idx := strings.Index(raw, ","); idx != -1 && strings.HasPrefix(raw, "data:") {
		raw = raw[idx+1:]
	}
	bin, err := base64.StdEncoding.DecodeString(raw)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid base64: "+err.Error())
		return
	}
	if len(bin) == 0 {
		writeError(w, http.StatusBadRequest, "empty image")
		return
	}
	if len(bin) > maxAvatarBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "avatar prea mare; max 256KB dupa resize")
		return
	}
	if err := h.users.SetAvatar(r.Context(), uid, bin, mime); err != nil {
		log.Printf("set avatar: %v", err)
		writeError(w, http.StatusInternalServerError, "avatar save failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"has_avatar": true})
}

// DeleteMyAvatar elimina avatarul userului curent.
func (h *UsersHandler) DeleteMyAvatar(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	if err := h.users.ClearAvatar(r.Context(), uid); err != nil {
		log.Printf("delete avatar: %v", err)
		writeError(w, http.StatusInternalServerError, "avatar delete failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"has_avatar": false})
}

// GetUserAvatar serveste binarul avatarului unui utilizator. Acces permis daca
// requesterul imparte cel putin un studiu cu target-ul (sau e super-admin).
func (h *UsersHandler) GetUserAvatar(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	target, err := uuid.Parse(chi.URLParam(r, "userId"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}
	allowed, err := h.canViewProfile(r, uid, target)
	if err != nil {
		log.Printf("avatar auth: %v", err)
		writeError(w, http.StatusInternalServerError, "authorization check failed")
		return
	}
	if !allowed {
		writeError(w, http.StatusForbidden, "no shared study with target user")
		return
	}
	data, mime, err := h.users.GetAvatar(r.Context(), target)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "avatar not set")
			return
		}
		log.Printf("get avatar: %v", err)
		writeError(w, http.StatusInternalServerError, "avatar lookup failed")
		return
	}
	if mime == "" {
		mime = "application/octet-stream"
	}
	w.Header().Set("Content-Type", mime)
	w.Header().Set("Cache-Control", "private, max-age=300")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

// GetUserProfile returneaza profilul unui alt utilizator, daca exista studiu comun.
func (h *UsersHandler) GetUserProfile(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	target, err := uuid.Parse(chi.URLParam(r, "userId"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}
	allowed, err := h.canViewProfile(r, uid, target)
	if err != nil {
		log.Printf("profile auth: %v", err)
		writeError(w, http.StatusInternalServerError, "authorization check failed")
		return
	}
	if !allowed {
		writeError(w, http.StatusForbidden, "no shared study with target user")
		return
	}
	profile, err := h.users.GetProfile(r.Context(), target)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		log.Printf("get profile: %v", err)
		writeError(w, http.StatusInternalServerError, "profile lookup failed")
		return
	}
	writeJSON(w, http.StatusOK, profile)
}

// MyCollaborators returneaza, pentru fiecare studiu in care userul curent e
// membru, lista celorlalti membri cu rolurile lor.
func (h *UsersHandler) MyCollaborators(w http.ResponseWriter, r *http.Request) {
	uid, ok := authmw.UserIDFrom(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing user context")
		return
	}
	groups, err := h.users.ListCollaboratorsByStudy(r.Context(), uid)
	if err != nil {
		log.Printf("collaborators: %v", err)
		writeError(w, http.StatusInternalServerError, "collaborators lookup failed")
		return
	}
	writeJSON(w, http.StatusOK, groups)
}

// canViewProfile decide daca uid are voie sa vada profilul target-ului.
// Super-admin trece intotdeauna; altfel verifica daca au cel putin un studiu comun.
func (h *UsersHandler) canViewProfile(r *http.Request, uid, target uuid.UUID) (bool, error) {
	if uid == target {
		return true, nil
	}
	requester, err := h.users.GetByID(r.Context(), uid)
	if err == nil && requester.IsSuperAdmin {
		return true, nil
	}
	return h.users.HasSharedStudy(r.Context(), uid, target)
}

func validateProfileUpdate(in *models.UserProfileUpdate) error {
	if in.FullName != nil {
		v := strings.TrimSpace(*in.FullName)
		if len(v) > 160 {
			return errors.New("full_name max 160 caractere")
		}
		*in.FullName = v
	}
	if in.Affiliation != nil {
		v := strings.TrimSpace(*in.Affiliation)
		if len(v) > 200 {
			return errors.New("affiliation max 200 caractere")
		}
		*in.Affiliation = v
	}
	if in.Bio != nil {
		v := strings.TrimSpace(*in.Bio)
		if len(v) > 1000 {
			return errors.New("bio max 1000 caractere")
		}
		*in.Bio = v
	}
	return nil
}
