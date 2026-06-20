package repository

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type BenchmarkRepository struct {
	pool *pgxpool.Pool
}

func NewBenchmarkRepository(pool *pgxpool.Pool) *BenchmarkRepository {
	return &BenchmarkRepository{pool: pool}
}

// AggregateByModelAndLanguage returneaza statistici de benchmark filtrate
// pe un studiu specific.
func (r *BenchmarkRepository) AggregateByModelAndLanguage(ctx context.Context, studyID uuid.UUID) ([]models.BenchmarkAggregate, error) {
	const q = `
		SELECT
			s.model_type,
			s.language,
			COUNT(*)::int AS run_count,
			percentile_cont(0.5) WITHIN GROUP (ORDER BY b.wall_time_ms)   AS median_wall_ms,
			percentile_cont(0.95) WITHIN GROUP (ORDER BY b.wall_time_ms)  AS p95_wall_ms,
			percentile_cont(0.5) WITHIN GROUP (ORDER BY b.cpu_time_ms)    AS median_cpu_ms,
			percentile_cont(0.5) WITHIN GROUP (ORDER BY b.peak_memory_mb) AS median_memory_mb
		FROM benchmarks b
		JOIN simulation_runs s ON s.id = b.simulation_id
		WHERE s.status = 'completed' AND s.study_id = $1
		GROUP BY s.model_type, s.language
		ORDER BY s.model_type, s.language`

	rows, err := r.pool.Query(ctx, q, studyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.BenchmarkAggregate
	for rows.Next() {
		var a models.BenchmarkAggregate
		if err := rows.Scan(
			&a.ModelType, &a.Language, &a.RunCount, &a.MedianWallMs, &a.P95WallMs,
			&a.MedianCPUMs, &a.MedianMemoryMB,
		); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

// ListRunsForModelLanguage intoarce toate rularile finalizate pentru o
// combinatie (model x limbaj) intr-un studiu, cu metadata necesara paginii
// de detaliu (dataset, t_max, timestamps, metrici per rulare).
func (r *BenchmarkRepository) ListRunsForModelLanguage(
	ctx context.Context, studyID uuid.UUID, modelType, language string,
) ([]models.BenchmarkRun, error) {
	const q = `
		SELECT
			s.id, s.dataset_id, d.name,
			s.t_max,
			b.wall_time_ms, b.cpu_time_ms, b.peak_memory_mb,
			s.created_at, s.completed_at
		FROM benchmarks b
		JOIN simulation_runs s ON s.id = b.simulation_id
		JOIN datasets d        ON d.id = s.dataset_id
		WHERE s.status = 'completed'
		  AND s.study_id = $1
		  AND s.model_type = $2
		  AND s.language = $3
		ORDER BY s.created_at DESC`

	rows, err := r.pool.Query(ctx, q, studyID, modelType, language)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.BenchmarkRun
	for rows.Next() {
		var b models.BenchmarkRun
		if err := rows.Scan(
			&b.SimulationID, &b.DatasetID, &b.DatasetName,
			&b.TMax,
			&b.WallTimeMs, &b.CPUTimeMs, &b.PeakMemoryMB,
			&b.CreatedAt, &b.CompletedAt,
		); err != nil {
			return nil, err
		}
		out = append(out, b)
	}
	return out, rows.Err()
}
