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

	log.Printf("DEBUG: DatabaseURL=%q", cfg.DatabaseURL)
	log.Printf("DEBUG: RedisURL=%q", cfg.RedisURL)

	ctx := context.Background()

	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("postgres pool: %v", err)
	}
	defer pool.Close()
	startPingCtx, cancelDB := context.WithTimeout(ctx, 15*time.Second)
	if err := pool.Ping(startPingCtx); err != nil {
		cancelDB()
		log.Fatalf("postgres ping: %v", err)
	}
	cancelDB()
	log.Printf("DEBUG: postgres ping OK")

	redisOpts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		log.Fatalf("redis url: %v", err)
	}
	rdb := redis.NewClient(redisOpts)
	defer rdb.Close()
	rStartCtx, cancelR := context.WithTimeout(ctx, 15*time.Second)
	if err := rdb.Ping(rStartCtx).Err(); err != nil {
		cancelR()
		log.Fatalf("redis ping: %v", err)
	}
	cancelR()
	log.Printf("DEBUG: redis ping OK")

	users := repository.NewUserRepository(pool)
	studies := repository.NewStudyRepository(pool)
	members := repository.NewStudyMemberRepository(pool)
	datasets := repository.NewDatasetRepository(pool)
	sims := repository.NewSimulationRepository(pool)
	results := repository.NewResultsRepository(pool)
	benches := repository.NewBenchmarkRepository(pool)

	dispatcher := runner.NewDispatcher(rdb)
	jwt := authmw.NewJWTMiddleware(cfg.JWTSecret)
	rbac := authmw.NewRBAC(users, members)

	deps := router.Deps{
		Health:      handlers.NewHealthHandler(pool, rdb),
		Auth:        handlers.NewAuthHandler(users, cfg.JWTSecret, cfg.JWTExpiry, cfg.BcryptCost),
		Users:       handlers.NewUsersHandler(users, studies),
		Studies:     handlers.NewStudiesHandler(studies, members, users),
		Datasets:    handlers.NewDatasetsHandler(datasets, cfg.MaxUploadBytes),
		Simulations: handlers.NewSimulationsHandler(sims, datasets, results, benches, dispatcher),
		Benchmarks:  handlers.NewBenchmarksHandler(benches),
		Admin:       handlers.NewAdminHandler(users, studies, pool),
		JWT:         jwt,
		RBAC:        rbac,
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
