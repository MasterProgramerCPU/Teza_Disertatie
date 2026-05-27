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

// ScriptDraftRepository expune CRUD pe draft-urile de cod, filtrate strict
// pe (user_id, study_id) pentru a asigura izolarea intre utilizatori.
type ScriptDraftRepository struct {
	pool *pgxpool.Pool
}

func NewScriptDraftRepository(pool *pgxpool.Pool) *ScriptDraftRepository {
	return &ScriptDraftRepository{pool: pool}
}

const scriptDraftCols = `id, user_id, study_id, name, description,
		script_content, parameters_json, created_at, updated_at`

func (r *ScriptDraftRepository) Create(ctx context.Context,
	userID, studyID uuid.UUID, name, description, scriptContent string,
	parametersJSON map[string]any) (*models.ScriptDraft, error) {

	paramJSON, err := json.Marshal(parametersJSON)
	if err != nil {
		return nil, err
	}

	var out models.ScriptDraft
	var paramRaw []byte
	err = r.pool.QueryRow(ctx, `
		INSERT INTO script_drafts (user_id, study_id, name, description,
		                           script_content, parameters_json)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING `+scriptDraftCols,
		userID, studyID, name, description, scriptContent, paramJSON,
	).Scan(
		&out.ID, &out.UserID, &out.StudyID, &out.Name, &out.Description,
		&out.ScriptContent, &paramRaw, &out.CreatedAt, &out.UpdatedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return nil, ErrDuplicate
		}
		return nil, err
	}
	_ = json.Unmarshal(paramRaw, &out.ParametersJSON)
	return &out, nil
}

func (r *ScriptDraftRepository) ListByUserStudy(ctx context.Context,
	userID, studyID uuid.UUID) ([]models.ScriptDraft, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT `+scriptDraftCols+`
		  FROM script_drafts WHERE user_id = $1 AND study_id = $2
		ORDER BY updated_at DESC`, userID, studyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []models.ScriptDraft
	for rows.Next() {
		d, err := scanScriptDraft(rows)
		if err != nil {
			return nil, err
		}
		// In listare, ascundem script_content pentru raspunsuri compacte;
		// frontend-ul il cere explicit cu GET pe id cand deschide draft-ul.
		d.ScriptContent = ""
		out = append(out, *d)
	}
	return out, rows.Err()
}

// Get returneaza draft-ul daca apartine utilizatorului si studiului date
// (filtrare cumulativa anti-IDOR).
func (r *ScriptDraftRepository) Get(ctx context.Context,
	userID, studyID, id uuid.UUID) (*models.ScriptDraft, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT `+scriptDraftCols+`
		  FROM script_drafts WHERE id = $1 AND user_id = $2 AND study_id = $3`,
		id, userID, studyID)
	d, err := scanScriptDraft(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return d, err
}

func (r *ScriptDraftRepository) Update(ctx context.Context,
	userID, studyID, id uuid.UUID,
	name, description, scriptContent string,
	parametersJSON map[string]any) (*models.ScriptDraft, error) {

	paramJSON, err := json.Marshal(parametersJSON)
	if err != nil {
		return nil, err
	}
	var out models.ScriptDraft
	var paramRaw []byte
	err = r.pool.QueryRow(ctx, `
		UPDATE script_drafts
		   SET name = $4, description = $5,
		       script_content = $6, parameters_json = $7,
		       updated_at = NOW()
		 WHERE id = $1 AND user_id = $2 AND study_id = $3
		 RETURNING `+scriptDraftCols,
		id, userID, studyID, name, description, scriptContent, paramJSON,
	).Scan(
		&out.ID, &out.UserID, &out.StudyID, &out.Name, &out.Description,
		&out.ScriptContent, &paramRaw, &out.CreatedAt, &out.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return nil, ErrDuplicate
		}
		return nil, err
	}
	_ = json.Unmarshal(paramRaw, &out.ParametersJSON)
	return &out, nil
}

func (r *ScriptDraftRepository) Delete(ctx context.Context,
	userID, studyID, id uuid.UUID) error {
	tag, err := r.pool.Exec(ctx,
		`DELETE FROM script_drafts WHERE id = $1 AND user_id = $2 AND study_id = $3`,
		id, userID, studyID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func scanScriptDraft(s scanner) (*models.ScriptDraft, error) {
	var d models.ScriptDraft
	var paramRaw []byte
	err := s.Scan(
		&d.ID, &d.UserID, &d.StudyID, &d.Name, &d.Description,
		&d.ScriptContent, &paramRaw, &d.CreatedAt, &d.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	_ = json.Unmarshal(paramRaw, &d.ParametersJSON)
	return &d, nil
}
