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

	// Configurare pentru runner-ele plug-in. Cand RunnerDeployEnabled=false,
	// crearea runner-elor in DB reuseste dar nu se face provisioning K8s
	// (modul dev local fara cluster). Cand true, API-ul foloseste InClusterConfig.
	RunnerDeployEnabled   bool
	RunnerNamespace       string
	RunnerCustomImage     string
	RunnerConfigMap       string
	RunnerSecret          string
	RunnerImagePullSecret string
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

	cfg.RunnerDeployEnabled = getEnv("RUNNER_DEPLOY_ENABLED", "false") == "true"
	cfg.RunnerNamespace = getEnv("RUNNER_NAMESPACE", "epimodel")
	cfg.RunnerCustomImage = getEnv("RUNNER_CUSTOM_IMAGE", "ghcr.io/masterprogramercpu/emedicine-runner-custom:latest")
	cfg.RunnerConfigMap = getEnv("RUNNER_CONFIGMAP", "epimodel-config")
	cfg.RunnerSecret = getEnv("RUNNER_SECRET", "epimodel-secrets")
	cfg.RunnerImagePullSecret = getEnv("RUNNER_IMAGE_PULL_SECRET", "ghcr-pull")

	return cfg, nil
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
