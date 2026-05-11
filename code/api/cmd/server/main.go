package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/tudorgeana/emedicine-api/internal/api/handlers"
	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/api/router"
	"github.com/tudorgeana/emedicine-api/internal/config"
	"github.com/tudorgeana/emedicine-api/internal/db/repository"
	"github.com/tudorgeana/emedicine-api/internal/runner"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	ctx := context.Background()

	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("postgres pool: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		log.Fatalf("postgres ping: %v", err)
	}

	redisOpts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		log.Fatalf("redis url: %v", err)
	}
	rdb := redis.NewClient(redisOpts)
	defer rdb.Close()
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("redis ping: %v", err)
	}

	users := repository.NewUserRepository(pool)
	datasets := repository.NewDatasetRepository(pool)
	sims := repository.NewSimulationRepository(pool)
	results := repository.NewResultsRepository(pool)
	benches := repository.NewBenchmarkRepository(pool)

	dispatcher := runner.NewDispatcher(rdb)
	jwt := authmw.NewJWTMiddleware(cfg.JWTSecret)

	deps := router.Deps{
		Health:      handlers.NewHealthHandler(pool, rdb),
		Auth:        handlers.NewAuthHandler(users, cfg.JWTSecret, cfg.JWTExpiry, cfg.BcryptCost),
		Datasets:    handlers.NewDatasetsHandler(datasets, cfg.MaxUploadBytes),
		Simulations: handlers.NewSimulationsHandler(sims, datasets, results, benches, dispatcher),
		Benchmarks:  handlers.NewBenchmarksHandler(benches),
		JWT:         jwt,
	}

	srv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           router.New(deps),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("listening on %s", cfg.HTTPAddr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("listen: %v", err)
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh
	log.Println("shutting down")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown: %v", err)
	}
}
