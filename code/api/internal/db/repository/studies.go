package repository

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type StudyRepository struct {
	pool *pgxpool.Pool
}

func NewStudyRepository(pool *pgxpool.Pool) *StudyRepository {
	return &StudyRepository{pool: pool}
}

func (r *StudyRepository) Create(ctx context.Context, name, diseaseCode, description string, createdBy uuid.UUID) (*models.Study, error) {
	const q = `
		INSERT INTO studies (name, disease_code, description, created_by)
		VALUES ($1, $2, NULLIF($3, ''), $4)
		RETURNING id, name, disease_code, COALESCE(description, ''), created_by, created_at, updated_at`

	var s models.Study
	err := r.pool.QueryRow(ctx, q, name, diseaseCode, description, createdBy).Scan(
		&s.ID, &s.Name, &s.DiseaseCode, &s.Description, &s.CreatedBy, &s.CreatedAt, &s.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return &s, nil
}

func (r *StudyRepository) GetByID(ctx context.Context, id uuid.UUID) (*models.Study, error) {
	const q = `
		SELECT id, name, disease_code, COALESCE(description, ''), created_by, created_at, updated_at
		FROM studies WHERE id = $1`

	var s models.Study
	err := r.pool.QueryRow(ctx, q, id).Scan(
		&s.ID, &s.Name, &s.DiseaseCode, &s.Description, &s.CreatedBy, &s.CreatedAt, &s.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &s, nil
}

func (r *StudyRepository) Update(ctx context.Context, id uuid.UUID, name, diseaseCode, description string) (*models.Study, error) {
	const q = `
		UPDATE studies
		SET name = $2, disease_code = $3, description = NULLIF($4, ''), updated_at = NOW()
		WHERE id = $1
		RETURNING id, name, disease_code, COALESCE(description, ''), created_by, created_at, updated_at`

	var s models.Study
	err := r.pool.QueryRow(ctx, q, id, name, diseaseCode, description).Scan(
		&s.ID, &s.Name, &s.DiseaseCode, &s.Description, &s.CreatedBy, &s.CreatedAt, &s.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &s, nil
}

func (r *StudyRepository) Delete(ctx context.Context, id uuid.UUID) error {
	const q = `DELETE FROM studies WHERE id = $1`
	tag, err := r.pool.Exec(ctx, q, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// CountAll returneaza nr. total de studii.
func (r *StudyRepository) CountAll(ctx context.Context) (int, error) {
	var n int
	if err := r.pool.QueryRow(ctx, `SELECT COUNT(*) FROM studies`).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}

// ListAll returneaza toate studiile (folosit de super admin).
func (r *StudyRepository) ListAll(ctx context.Context) ([]models.Study, error) {
	const q = `
		SELECT id, name, disease_code, COALESCE(description, ''), created_by, created_at, updated_at
		FROM studies ORDER BY created_at DESC`

	rows, err := r.pool.Query(ctx, q)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.Study
	for rows.Next() {
		var s models.Study
		if err := rows.Scan(&s.ID, &s.Name, &s.DiseaseCode, &s.Description, &s.CreatedBy, &s.CreatedAt, &s.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

// ListForUser returneaza studiile in care userul e membru, impreuna cu rolul.
func (r *StudyRepository) ListForUser(ctx context.Context, userID uuid.UUID) ([]models.MembershipForUser, error) {
	const q = `
		SELECT s.id, s.name, s.disease_code, COALESCE(s.description, ''), s.created_by, s.created_at, s.updated_at, m.role
		FROM studies s
		JOIN study_members m ON m.study_id = s.id
		WHERE m.user_id = $1
		ORDER BY s.created_at DESC`

	rows, err := r.pool.Query(ctx, q, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.MembershipForUser
	for rows.Next() {
		var s models.Study
		var role string
		if err := rows.Scan(&s.ID, &s.Name, &s.DiseaseCode, &s.Description, &s.CreatedBy, &s.CreatedAt, &s.UpdatedAt, &role); err != nil {
			return nil, err
		}
		out = append(out, models.MembershipForUser{Study: s, Role: models.StudyRole(role)})
	}
	return out, rows.Err()
}
