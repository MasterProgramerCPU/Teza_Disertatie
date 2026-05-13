package router

import (
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/tudorgeana/emedicine-api/internal/api/handlers"
	authmw "github.com/tudorgeana/emedicine-api/internal/api/middleware"
	"github.com/tudorgeana/emedicine-api/internal/models"
)

type Deps struct {
	Health      *handlers.HealthHandler
	Auth        *handlers.AuthHandler
	Users       *handlers.UsersHandler
	Studies     *handlers.StudiesHandler
	Datasets    *handlers.DatasetsHandler
	Simulations *handlers.SimulationsHandler
	Benchmarks  *handlers.BenchmarksHandler
	Admin       *handlers.AdminHandler
	JWT         *authmw.JWTMiddleware
	RBAC        *authmw.RBAC
}

func New(deps Deps) http.Handler {
	r := chi.NewRouter()

	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(60 * time.Second))
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
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

		// Toate rutele de mai jos cer autentificare.
		r.Group(func(r chi.Router) {
			r.Use(deps.JWT.Authenticate)

			// Profilul userului curent
			r.Get("/me", deps.Users.Me)

			// Studii — list / create sunt scope pe userul curent
			r.Route("/studies", func(r chi.Router) {
				r.Get("/", deps.Studies.List)
				r.Post("/", deps.Studies.Create)

				// Rute care lucreaza intr-un studiu specific
				r.Route("/{studyId}", func(r chi.Router) {
					// Membership minim (orice rol) — citire
					r.Group(func(r chi.Router) {
						r.Use(deps.RBAC.RequireStudyMembership())

						r.Get("/", deps.Studies.Get)
						r.Get("/members", deps.Studies.ListMembers)

						// Datasets — citire pentru toti membrii
						r.Get("/datasets", deps.Datasets.List)
						r.Get("/datasets/{id}", deps.Datasets.Get)

						// Simulations — citire pentru toti membrii
						r.Get("/simulations", deps.Simulations.List)
						r.Get("/simulations/{id}", deps.Simulations.Get)
						r.Get("/simulations/{id}/results", deps.Simulations.Results)
						r.Get("/simulations/{id}/export", deps.Simulations.Export)

						// Benchmarks — citire pentru toti membrii
						r.Get("/benchmarks", deps.Benchmarks.Aggregate)
					})

					// Datasets — scriere: admin sau contributor
					r.Group(func(r chi.Router) {
						r.Use(deps.RBAC.RequireStudyMembership(models.RoleAdmin, models.RoleContributor))
						r.Post("/datasets", deps.Datasets.Create)
						r.Delete("/datasets/{id}", deps.Datasets.Delete)
					})

					// Simulations — scriere: admin sau researcher
					r.Group(func(r chi.Router) {
						r.Use(deps.RBAC.RequireStudyMembership(models.RoleAdmin, models.RoleResearcher))
						r.Post("/simulations", deps.Simulations.Create)
					})

					// Admin studiu — doar rolul admin
					r.Group(func(r chi.Router) {
						r.Use(deps.RBAC.RequireStudyMembership(models.RoleAdmin))
						r.Patch("/", deps.Studies.Update)
						r.Delete("/", deps.Studies.Delete)
						r.Post("/members", deps.Studies.AddMember)
						r.Patch("/members/{userId}", deps.Studies.UpdateMemberRole)
						r.Delete("/members/{userId}", deps.Studies.RemoveMember)
					})
				})
			})

			// Endpoint-uri super admin
			r.Route("/admin", func(r chi.Router) {
				r.Use(deps.RBAC.RequireSuperAdmin)
				r.Get("/stats", deps.Admin.Stats)
				r.Get("/users", deps.Admin.ListUsers)
				r.Patch("/users/{userId}/super-admin", deps.Admin.SetSuperAdmin)
				r.Get("/studies", deps.Admin.ListStudies)
			})
		})
	})

	return r
}
