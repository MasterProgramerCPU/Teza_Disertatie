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
	"github.com/tudorgeana/emedicine-api/internal/k8s"
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
	startPingCtx, cancelDB := context.WithTimeout(ctx, 15*time.Second)
	if err := pool.Ping(startPingCtx); err != nil {
		cancelDB()
		log.Fatalf("postgres ping: %v", err)
	}
	cancelDB()

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

	users := repository.NewUserRepository(pool)
	studies := repository.NewStudyRepository(pool)
	members := repository.NewStudyMemberRepository(pool)
	datasets := repository.NewDatasetRepository(pool)
	sims := repository.NewSimulationRepository(pool)
	results := repository.NewResultsRepository(pool)
	benches := repository.NewBenchmarkRepository(pool)
	runners := repository.NewRunnerRepository(pool)
	scriptDrafts := repository.NewScriptDraftRepository(pool)

	dispatcher := runner.NewDispatcher(rdb)
	jwt := authmw.NewJWTMiddleware(cfg.JWTSecret)
	rbac := authmw.NewRBAC(users, members)

	k8sMgr, err := k8s.New(k8s.Config{
		Enabled:    cfg.RunnerDeployEnabled,
		Namespace:  cfg.RunnerNamespace,
		Image:      cfg.RunnerCustomImage,
		ConfigMap:  cfg.RunnerConfigMap,
		SecretName: cfg.RunnerSecret,
		PullSecret: cfg.RunnerImagePullSecret,
	})
	if err != nil {
		log.Fatalf("k8s manager: %v", err)
	}
	if k8sMgr.Enabled() {
		log.Printf("runner provisioning enabled (namespace=%s, image=%s)",
			cfg.RunnerNamespace, cfg.RunnerCustomImage)
	} else {
		log.Printf("runner provisioning disabled (dev mode)")
	}

	deps := router.Deps{
		Health:       handlers.NewHealthHandler(pool, rdb),
		Auth:         handlers.NewAuthHandler(users, cfg.JWTSecret, cfg.JWTExpiry, cfg.BcryptCost),
		Users:        handlers.NewUsersHandler(users, studies),
		Studies:      handlers.NewStudiesHandler(studies, members, users),
		Datasets:     handlers.NewDatasetsHandler(datasets, cfg.MaxUploadBytes),
		Simulations:  handlers.NewSimulationsHandler(sims, datasets, results, benches, dispatcher),
		Benchmarks:   handlers.NewBenchmarksHandler(benches),
		Admin:        handlers.NewAdminHandler(users, studies, pool),
		Runners:      handlers.NewRunnersHandler(runners, k8sMgr),
		ScriptDrafts: handlers.NewScriptDraftsHandler(scriptDrafts),
		Map:          handlers.NewMapHandler(pool),
		JWT:          jwt,
		RBAC:         rbac,
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
