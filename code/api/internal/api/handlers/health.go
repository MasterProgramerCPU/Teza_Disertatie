package handlers

import (
	"context"
	"log"
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

	dbErr := h.DB.Ping(ctx)
	redisErr := h.Redis.Ping(ctx).Err()
	if dbErr != nil {
		log.Printf("health: db ping error: %v", dbErr)
	}
	if redisErr != nil {
		log.Printf("health: redis ping error: %v", redisErr)
	}
	dbOK := dbErr == nil
	redisOK := redisErr == nil

	status := http.StatusOK
	overall := "ok"
	if !dbOK || !redisOK {
		status = http.StatusServiceUnavailable
		overall = "degraded"
	}

	writeJSON(w, status, map[string]any{
		"status":   overall,
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
