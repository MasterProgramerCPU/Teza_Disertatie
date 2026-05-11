package handlers

import (
	"context"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type HealthHandler struct {
	DB    *pgxpool.Pool
	Redis *redis.Client
}

func NewHealthHandler(db *pgxpool.Pool, rdb *redis.Client) *HealthHandler {
	return &HealthHandler{DB: db, Redis: rdb}
}

func (h *HealthHandler) Get(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	dbOK := h.DB.Ping(ctx) == nil
	redisOK := h.Redis.Ping(ctx).Err() == nil

	status := http.StatusOK
	if !dbOK || !redisOK {
		status = http.StatusServiceUnavailable
	}

	writeJSON(w, status, map[string]any{
		"status":   "ok",
		"database": boolStatus(dbOK),
		"redis":    boolStatus(redisOK),
	})
}

func boolStatus(ok bool) string {
	if ok {
		return "up"
	}
	return "down"
}
