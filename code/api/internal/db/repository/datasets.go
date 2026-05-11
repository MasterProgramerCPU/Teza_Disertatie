package repository

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type DatasetRepository struct {
	pool *pgxpool.Pool
}

func NewDatasetRepository(pool *pgxpool.Pool) *DatasetRepository {
	return &DatasetRepository{pool: pool}
}

func (r *DatasetRepository) Create(ctx context.Context, userID uuid.UUID, name, diseaseCode string, records []models.EpidemiologicalRecord) (*models.Dataset, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var d models.Dataset
	err = tx.QueryRow(ctx, `
		INSERT INTO datasets (user_id, name, disease_code, record_count)
		VALUES ($1, $2, $3, $4)
		RETURNING id, user_id, name, disease_code, uploaded_at, record_count`,
		userID, name, diseaseCode, len(records),
	).Scan(&d.ID, &d.UserID, &d.Name, &d.DiseaseCode, &d.UploadedAt, &d.RecordCount)
	if err != nil {
		return nil, err
	}

	if len(records) > 0 {
		rows := make([][]any, len(records))
		for i, rec := range records {
			rows[i] = []any{d.ID, rec.RecordedDate, rec.RegionCode, rec.Susceptible, rec.Infected, rec.Recovered, rec.Population}
		}
		_, err = tx.CopyFrom(ctx,
			pgx.Identifier{"epidemiological_records"},
			[]string{"dataset_id", "recorded_date", "region_code", "susceptible", "infected", "recovered", "population"},
			pgx.CopyFromRows(rows),
		)
		if err != nil {
			return nil, err
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &d, nil
}

func (r *DatasetRepository) ListByUser(ctx context.Context, userID uuid.UUID) ([]models.Dataset, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, user_id, name, disease_code, uploaded_at, record_count
		FROM datasets WHERE user_id = $1 ORDER BY uploaded_at DESC`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.Dataset
	for rows.Next() {
		var d models.Dataset
		if err := rows.Scan(&d.ID, &d.UserID, &d.Name, &d.DiseaseCode, &d.UploadedAt, &d.RecordCount); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func (r *DatasetRepository) Get(ctx context.Context, userID, id uuid.UUID) (*models.Dataset, error) {
	var d models.Dataset
	err := r.pool.QueryRow(ctx, `
		SELECT id, user_id, name, disease_code, uploaded_at, record_count
		FROM datasets WHERE id = $1 AND user_id = $2`,
		id, userID,
	).Scan(&d.ID, &d.UserID, &d.Name, &d.DiseaseCode, &d.UploadedAt, &d.RecordCount)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &d, nil
}

func (r *DatasetRepository) Delete(ctx context.Context, userID, id uuid.UUID) error {
	tag, err := r.pool.Exec(ctx, `DELETE FROM datasets WHERE id = $1 AND user_id = $2`, id, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *DatasetRepository) FirstRecord(ctx context.Context, datasetID uuid.UUID) (*models.EpidemiologicalRecord, error) {
	var rec models.EpidemiologicalRecord
	err := r.pool.QueryRow(ctx, `
		SELECT id, dataset_id, recorded_date, region_code, susceptible, infected, recovered, population
		FROM epidemiological_records WHERE dataset_id = $1
		ORDER BY recorded_date ASC LIMIT 1`, datasetID).Scan(
		&rec.ID, &rec.DatasetID, &rec.RecordedDate, &rec.RegionCode,
		&rec.Susceptible, &rec.Infected, &rec.Recovered, &rec.Population,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &rec, nil
}
