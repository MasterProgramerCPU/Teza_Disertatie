package repository

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type SimulationRepository struct {
	pool *pgxpool.Pool
}

func NewSimulationRepository(pool *pgxpool.Pool) *SimulationRepository {
	return &SimulationRepository{pool: pool}
}

func (r *SimulationRepository) Create(ctx context.Context, run *models.SimulationRun) (*models.SimulationRun, error) {
	paramsJSON, err := json.Marshal(run.Parameters)
	if err != nil {
		return nil, err
	}

	// script_content este NULL pentru modelele compartimentale si LSTM, si
	// non-null doar pentru model_type='script' (CHECK la nivel de DB).
	var scriptArg any
	if run.ScriptContent != "" {
		scriptArg = run.ScriptContent
	}

	const q = `
		INSERT INTO simulation_runs (user_id, study_id, dataset_id, model_type, language, parameters, population_n, t_max, script_content, status)
		VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, 'pending')
		RETURNING id, user_id, study_id, dataset_id, model_type, language, parameters, population_n, t_max, COALESCE(script_content,''), status, created_at`

	var out models.SimulationRun
	var params []byte
	err = r.pool.QueryRow(ctx, q,
		run.UserID, run.StudyID, run.DatasetID, run.ModelType, run.Language, paramsJSON, run.PopulationN, run.TMax, scriptArg,
	).Scan(
		&out.ID, &out.UserID, &out.StudyID, &out.DatasetID, &out.ModelType, &out.Language, &params,
		&out.PopulationN, &out.TMax, &out.ScriptContent, &out.Status, &out.CreatedAt,
	)
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(params, &out.Parameters); err != nil {
		return nil, err
	}
	return &out, nil
}

func (r *SimulationRepository) ListByStudy(ctx context.Context, studyID uuid.UUID) ([]models.SimulationRun, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, user_id, study_id, dataset_id, model_type, language, parameters, population_n, t_max,
		       status, error_message, created_at, completed_at
		FROM simulation_runs WHERE study_id = $1 ORDER BY created_at DESC`, studyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.SimulationRun
	for rows.Next() {
		var s models.SimulationRun
		var params []byte
		if err := rows.Scan(
			&s.ID, &s.UserID, &s.StudyID, &s.DatasetID, &s.ModelType, &s.Language, &params,
			&s.PopulationN, &s.TMax, &s.Status, &s.ErrorMessage, &s.CreatedAt, &s.CompletedAt,
		); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(params, &s.Parameters); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

func (r *SimulationRepository) Get(ctx context.Context, studyID, id uuid.UUID) (*models.SimulationRun, error) {
	var s models.SimulationRun
	var params []byte
	err := r.pool.QueryRow(ctx, `
		SELECT id, user_id, study_id, dataset_id, model_type, language, parameters, population_n, t_max,
		       status, error_message, created_at, completed_at
		FROM simulation_runs WHERE id = $1 AND study_id = $2`,
		id, studyID,
	).Scan(
		&s.ID, &s.UserID, &s.StudyID, &s.DatasetID, &s.ModelType, &s.Language, &params,
		&s.PopulationN, &s.TMax, &s.Status, &s.ErrorMessage, &s.CreatedAt, &s.CompletedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(params, &s.Parameters); err != nil {
		return nil, err
	}
	return &s, nil
}

type ResultsRepository struct {
	pool *pgxpool.Pool
}

func NewResultsRepository(pool *pgxpool.Pool) *ResultsRepository {
	return &ResultsRepository{pool: pool}
}

func (r *ResultsRepository) ListBySimulation(ctx context.Context, simID uuid.UUID) ([]models.SimulationResult, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT simulation_id, t, compartments FROM simulation_results
		WHERE simulation_id = $1 ORDER BY t ASC`, simID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.SimulationResult
	for rows.Next() {
		var res models.SimulationResult
		var compartments []byte
		if err := rows.Scan(&res.SimulationID, &res.T, &compartments); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(compartments, &res.Compartments); err != nil {
			return nil, err
		}
		out = append(out, res)
	}
	return out, rows.Err()
}
