package repository

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type BenchmarkRepository struct {
	pool *pgxpool.Pool
}

func NewBenchmarkRepository(pool *pgxpool.Pool) *BenchmarkRepository {
	return &BenchmarkRepository{pool: pool}
}

func (r *BenchmarkRepository) AggregateByModelAndLanguage(ctx context.Context) ([]models.BenchmarkAggregate, error) {
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
		WHERE s.status = 'completed'
		GROUP BY s.model_type, s.language
		ORDER BY s.model_type, s.language`

	rows, err := r.pool.Query(ctx, q)
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
