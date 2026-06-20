package repository

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type DatasetRepository struct {
	pool *pgxpool.Pool
}

func NewDatasetRepository(pool *pgxpool.Pool) *DatasetRepository {
	return &DatasetRepository{pool: pool}
}

func (r *DatasetRepository) Create(ctx context.Context, studyID, userID uuid.UUID, name, diseaseCode string, records []models.EpidemiologicalRecord) (*models.Dataset, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var d models.Dataset
	err = tx.QueryRow(ctx, `
		INSERT INTO datasets (user_id, study_id, name, disease_code, record_count)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, user_id, study_id, name, disease_code, uploaded_at, record_count`,
		userID, studyID, name, diseaseCode, len(records),
	).Scan(&d.ID, &d.UserID, &d.StudyID, &d.Name, &d.DiseaseCode, &d.UploadedAt, &d.RecordCount)
	if err != nil {
		return nil, err
	}

	if len(records) > 0 {
		rows := make([][]any, len(records))
		for i, rec := range records {
			rows[i] = []any{
				d.ID, rec.RecordedDate, rec.RegionCode,
				rec.Susceptible, rec.Infected, rec.Recovered, rec.Population,
				// coloane epi extinse (toate optionale, NULL daca *int64/*float64 e nil)
				rec.Deaths, rec.NewCases, rec.NewDeaths,
				rec.Hospitalized, rec.ICU, rec.Vaccinated, rec.Tested,
				rec.StringencyIndex, rec.ReproductionRate,
			}
		}
		_, err = tx.CopyFrom(ctx,
			pgx.Identifier{"epidemiological_records"},
			[]string{
				"dataset_id", "recorded_date", "region_code",
				"susceptible", "infected", "recovered", "population",
				"deaths", "new_cases", "new_deaths",
				"hospitalized", "icu", "vaccinated", "tested",
				"stringency_index", "reproduction_rate",
			},
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

func (r *DatasetRepository) ListByStudy(ctx context.Context, studyID uuid.UUID) ([]models.Dataset, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, user_id, study_id, name, disease_code, uploaded_at, record_count
		FROM datasets WHERE study_id = $1 ORDER BY uploaded_at DESC`, studyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.Dataset
	for rows.Next() {
		var d models.Dataset
		if err := rows.Scan(&d.ID, &d.UserID, &d.StudyID, &d.Name, &d.DiseaseCode, &d.UploadedAt, &d.RecordCount); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func (r *DatasetRepository) Get(ctx context.Context, studyID, id uuid.UUID) (*models.Dataset, error) {
	var d models.Dataset
	err := r.pool.QueryRow(ctx, `
		SELECT id, user_id, study_id, name, disease_code, uploaded_at, record_count
		FROM datasets WHERE id = $1 AND study_id = $2`,
		id, studyID,
	).Scan(&d.ID, &d.UserID, &d.StudyID, &d.Name, &d.DiseaseCode, &d.UploadedAt, &d.RecordCount)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &d, nil
}

// Delete sterge un dataset din studiu. Daca requireOwner e adevarat, doar
// creatorul (user_id) il poate sterge; altfel, oricine cu permisiuni de admin
// in studiu (verificarea facuta in handler) poate sterge.
func (r *DatasetRepository) Delete(ctx context.Context, studyID, id uuid.UUID, ownerID *uuid.UUID) error {
	var (
		tag pgconn.CommandTag
		err error
	)
	if ownerID != nil {
		tag, err = r.pool.Exec(ctx, `DELETE FROM datasets WHERE id = $1 AND study_id = $2 AND user_id = $3`, id, studyID, *ownerID)
	} else {
		tag, err = r.pool.Exec(ctx, `DELETE FROM datasets WHERE id = $1 AND study_id = $2`, id, studyID)
	}
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// FirstRecord intoarce prima zi cu cazuri active (infected > 0). Asta
// permite ca seturile preprocesate prin fill_calendar (OWID COVID/mpox), care
// debuteaza cronologic cu zile plate I=0, sa porneasca simularea dintr-un
// punct de stare ne-trivial — altfel ODE-ul SIR/SEIR/SIDARTHE cu I(0)=0 este
// matematic un punct fix si traiectoria ramane plata la nesfarsit. Pentru
// seturile sintetice si OWID care raporteaza I>0 din prima zi, comportamentul
// e identic cu varianta veche.
//
// Fallback: daca dataset-ul are doar zile cu infected = 0 (caz de degenerare),
// intoarce totusi prima zi pentru a evita esecul cererii.
func (r *DatasetRepository) FirstRecord(ctx context.Context, datasetID uuid.UUID) (*models.EpidemiologicalRecord, error) {
	var rec models.EpidemiologicalRecord
	err := r.pool.QueryRow(ctx, `
		SELECT id, dataset_id, recorded_date, region_code, susceptible, infected, recovered, population
		FROM epidemiological_records WHERE dataset_id = $1 AND infected > 0
		ORDER BY recorded_date ASC LIMIT 1`, datasetID).Scan(
		&rec.ID, &rec.DatasetID, &rec.RecordedDate, &rec.RegionCode,
		&rec.Susceptible, &rec.Infected, &rec.Recovered, &rec.Population,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		// Fallback: nu exista zile cu I>0 → folosim prima zi cronologic.
		err = r.pool.QueryRow(ctx, `
			SELECT id, dataset_id, recorded_date, region_code, susceptible, infected, recovered, population
			FROM epidemiological_records WHERE dataset_id = $1
			ORDER BY recorded_date ASC LIMIT 1`, datasetID).Scan(
			&rec.ID, &rec.DatasetID, &rec.RecordedDate, &rec.RegionCode,
			&rec.Susceptible, &rec.Infected, &rec.Recovered, &rec.Population,
		)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
	}
	if err != nil {
		return nil, err
	}
	return &rec, nil
}
