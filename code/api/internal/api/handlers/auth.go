package handlers

import (
	"errors"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"

	"github.com/tudorgeana/emedicine-api/internal/db/repository"
)

type AuthHandler struct {
	users      *repository.UserRepository
	jwtSecret  []byte
	jwtExpiry  time.Duration
	bcryptCost int
	dummyHash  []byte
}

func NewAuthHandler(users *repository.UserRepository, jwtSecret string, jwtExpiry time.Duration, bcryptCost int) *AuthHandler {
	// Hash fals precalculat cu acelasi cost, folosit la login pentru a egaliza
	// timpul de raspuns cand emailul nu exista (vezi Login), prevenind enumerarea
	// utilizatorilor printr-un timing oracle.
	dummy, _ := bcrypt.GenerateFromPassword([]byte("invalid-placeholder-password"), bcryptCost)
	return &AuthHandler{
		users:      users,
		jwtSecret:  []byte(jwtSecret),
		jwtExpiry:  jwtExpiry,
		bcryptCost: bcryptCost,
		dummyHash:  dummy,
	}
}

type credentials struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (c *credentials) normalize() {
	c.Email = strings.ToLower(strings.TrimSpace(c.Email))
}

func (c *credentials) validate() error {
	if c.Email == "" || !strings.Contains(c.Email, "@") {
		return errors.New("invalid email")
	}
	if len(c.Password) < 8 {
		return errors.New("password must be at least 8 characters")
	}
	return nil
}

func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	var creds credentials
	if err := decodeJSON(r, &creds); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	creds.normalize()
	if err := creds.validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(creds.Password), h.bcryptCost)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "hash failure")
		return
	}

	user, err := h.users.Create(r.Context(), creds.Email, string(hash))
	if errors.Is(err, repository.ErrDuplicate) {
		writeError(w, http.StatusConflict, "email already registered")
		return
	}
	if err != nil {
		log.Printf("register: users.Create error: %v", err)
		writeError(w, http.StatusInternalServerError, "could not create user")
		return
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"id":         user.ID,
		"email":      user.Email,
		"created_at": user.CreatedAt,
	})
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var creds credentials
	if err := decodeJSON(r, &creds); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	creds.normalize()

	user, err := h.users.GetByEmail(r.Context(), creds.Email)
	if errors.Is(err, repository.ErrNotFound) {
		// Comparam cu hash-ul fals pentru a consuma acelasi timp ca un login
		// valid; altfel diferenta de latenta ar dezvalui ce emailuri exista.
		_ = bcrypt.CompareHashAndPassword(h.dummyHash, []byte(creds.Password))
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failure")
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(creds.Password)); err != nil {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}

	now := time.Now()
	claims := jwt.MapClaims{
		"sub": user.ID.String(),
		"iat": now.Unix(),
		"exp": now.Add(h.jwtExpiry).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(h.jwtSecret)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not sign token")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"token":          signed,
		"expires_at":     now.Add(h.jwtExpiry),
		"user_id":        user.ID,
		"email":          user.Email,
		"is_super_admin": user.IsSuperAdmin,
	})
}
