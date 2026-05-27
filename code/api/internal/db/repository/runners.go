package repository

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

// RunnerRepository gestioneaza tabela runners (plug-in-uri definite de
// utilizator, scope-uite pe studiu).
type RunnerRepository struct {
	pool *pgxpool.Pool
}

func NewRunnerRepository(pool *pgxpool.Pool) *RunnerRepository {
	return &RunnerRepository{pool: pool}
}

const runnerSelectCols = `id, study_id, uploaded_by, name, description,
		image, parameter_schema, status, status_message,
		queue_name, deployment_name, created_at, ready_at`

// Create insereaza un runner nou (strict mod imagine; image trebuie sa fie
// non-vid si CHECK-ul DB il valideaza si el).
func (r *RunnerRepository) Create(ctx context.Context, studyID, userID uuid.UUID,
	name, description, image string,
	parameterSchema map[string]any, queueName string) (*models.Runner, error) {

	schemaJSON, err := json.Marshal(parameterSchema)
	if err != nil {
		return nil, err
	}

	var out models.Runner
	var schemaRaw []byte
	err = r.pool.QueryRow(ctx, `
		INSERT INTO runners (study_id, uploaded_by, name, description,
		                     image, parameter_schema, queue_name)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		RETURNING `+runnerSelectCols,
		studyID, userID, name, description, image, schemaJSON, queueName,
	).Scan(
		&out.ID, &out.StudyID, &out.UploadedBy, &out.Name, &out.Description,
		&out.Image, &schemaRaw, &out.Status, &out.StatusMessage,
		&out.QueueName, &out.DeploymentName, &out.CreatedAt, &out.ReadyAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return nil, ErrDuplicate
		}
		return nil, err
	}
	_ = json.Unmarshal(schemaRaw, &out.ParameterSchema)
	return &out, nil
}

func (r *RunnerRepository) ListByStudy(ctx context.Context, studyID uuid.UUID) ([]models.Runner, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT `+runnerSelectCols+`
		FROM runners WHERE study_id = $1 ORDER BY created_at DESC`, studyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.Runner
	for rows.Next() {
		rn, err := scanRunner(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *rn)
	}
	return out, rows.Err()
}

// Get returneaza runner-ul daca apartine studiului dat (scoping anti-IDOR).
func (r *RunnerRepository) Get(ctx context.Context, studyID, id uuid.UUID) (*models.Runner, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT `+runnerSelectCols+`
		FROM runners WHERE id = $1 AND study_id = $2`, id, studyID)
	rn, err := scanRunner(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return rn, err
}

func (r *RunnerRepository) UpdateStatus(ctx context.Context, id uuid.UUID,
	status models.RunnerStatus, message, deploymentName string) error {
	// Cast explicit pe $2 ($2::text) — altfel YugabyteDB nu poate deduce un tip
	// unic pentru $2 cand e folosit atat in SET (varchar) cat si in CASE WHEN
	// $2 = 'ready' (text inferat din literal), si returneaza SQLSTATE 42P08.
	_, err := r.pool.Exec(ctx, `
		UPDATE runners
		   SET status = $2::text, status_message = $3,
		       deployment_name = COALESCE(NULLIF($4::text, ''), deployment_name),
		       ready_at = CASE WHEN $2::text = 'ready' AND ready_at IS NULL
		                       THEN NOW() ELSE ready_at END
		 WHERE id = $1`,
		id, status, message, deploymentName,
	)
	return err
}

func (r *RunnerRepository) Delete(ctx context.Context, studyID, id uuid.UUID) error {
	tag, err := r.pool.Exec(ctx,
		`DELETE FROM runners WHERE id = $1 AND study_id = $2`, id, studyID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// scanRunner accepta atat *pgx.Rows cat si pgx.Row (interfata Scan comuna).
type scanner interface {
	Scan(dest ...any) error
}

func scanRunner(s scanner) (*models.Runner, error) {
	var rn models.Runner
	var schemaRaw []byte
	err := s.Scan(
		&rn.ID, &rn.StudyID, &rn.UploadedBy, &rn.Name, &rn.Description,
		&rn.Image, &schemaRaw, &rn.Status, &rn.StatusMessage,
		&rn.QueueName, &rn.DeploymentName, &rn.CreatedAt, &rn.ReadyAt,
	)
	if err != nil {
		return nil, err
	}
	_ = json.Unmarshal(schemaRaw, &rn.ParameterSchema)
	return &rn, nil
}
