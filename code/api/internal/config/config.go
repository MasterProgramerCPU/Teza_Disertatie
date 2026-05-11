package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	HTTPAddr        string
	DatabaseURL     string
	RedisURL        string
	JWTSecret       string
	JWTExpiry       time.Duration
	BcryptCost      int
	MaxUploadBytes  int64
	ShutdownTimeout time.Duration
}

func Load() (*Config, error) {
	cfg := &Config{
		HTTPAddr:        getEnv("HTTP_ADDR", ":8080"),
		DatabaseURL:     getEnv("DATABASE_URL", "postgres://emedicine:emedicine@localhost:5433/emedicine?sslmode=disable"),
		RedisURL:        getEnv("REDIS_URL", "redis://localhost:6379/0"),
		JWTSecret:       getEnv("JWT_SECRET", ""),
		JWTExpiry:       24 * time.Hour,
		BcryptCost:      12,
		MaxUploadBytes:  32 << 20,
		ShutdownTimeout: 15 * time.Second,
	}

	if v := os.Getenv("JWT_EXPIRY_HOURS"); v != "" {
		h, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("JWT_EXPIRY_HOURS invalid: %w", err)
		}
		cfg.JWTExpiry = time.Duration(h) * time.Hour
	}

	if cfg.JWTSecret == "" {
		return nil, fmt.Errorf("JWT_SECRET must be set")
	}

	return cfg, nil
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
