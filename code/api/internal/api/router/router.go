package router

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/tudorgeana/emedicine-api/internal/api/handlers"
	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
)

type Deps struct {
	Health      *handlers.HealthHandler
	Auth        *handlers.AuthHandler
	Datasets    *handlers.DatasetsHandler
	Simulations *handlers.SimulationsHandler
	Benchmarks  *handlers.BenchmarksHandler
	JWT         *authmw.JWTMiddleware
}

func New(deps Deps) http.Handler {
	r := chi.NewRouter()

	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(60))
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type"},
		AllowCredentials: false,
		MaxAge:           300,
	}))

	r.Route("/api", func(r chi.Router) {
		r.Get("/health", deps.Health.Get)

		r.Route("/auth", func(r chi.Router) {
			r.Post("/register", deps.Auth.Register)
			r.Post("/login", deps.Auth.Login)
		})

		r.Group(func(r chi.Router) {
			r.Use(deps.JWT.Authenticate)

			r.Route("/datasets", func(r chi.Router) {
				r.Get("/", deps.Datasets.List)
				r.Post("/", deps.Datasets.Create)
				r.Get("/{id}", deps.Datasets.Get)
				r.Delete("/{id}", deps.Datasets.Delete)
			})

			r.Route("/simulations", func(r chi.Router) {
				r.Get("/", deps.Simulations.List)
				r.Post("/", deps.Simulations.Create)
				r.Get("/{id}", deps.Simulations.Get)
				r.Get("/{id}/results", deps.Simulations.Results)
				r.Get("/{id}/export", deps.Simulations.Export)
			})

			r.Get("/benchmarks", deps.Benchmarks.Aggregate)
		})
	})

	return r
}
