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

type StudyMemberRepository struct {
	pool *pgxpool.Pool
}

func NewStudyMemberRepository(pool *pgxpool.Pool) *StudyMemberRepository {
	return &StudyMemberRepository{pool: pool}
}

func (r *StudyMemberRepository) Add(ctx context.Context, studyID, userID uuid.UUID, role models.StudyRole) (*models.StudyMember, error) {
	const q = `
		INSERT INTO study_members (study_id, user_id, role)
		VALUES ($1, $2, $3)
		RETURNING study_id, user_id, role, joined_at`

	var m models.StudyMember
	var roleStr string
	err := r.pool.QueryRow(ctx, q, studyID, userID, string(role)).Scan(
		&m.StudyID, &m.UserID, &roleStr, &m.JoinedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return nil, ErrDuplicate
		}
		return nil, err
	}
	m.Role = models.StudyRole(roleStr)
	return &m, nil
}

func (r *StudyMemberRepository) UpdateRole(ctx context.Context, studyID, userID uuid.UUID, role models.StudyRole) error {
	const q = `UPDATE study_members SET role = $3 WHERE study_id = $1 AND user_id = $2`
	tag, err := r.pool.Exec(ctx, q, studyID, userID, string(role))
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *StudyMemberRepository) Remove(ctx context.Context, studyID, userID uuid.UUID) error {
	const q = `DELETE FROM study_members WHERE study_id = $1 AND user_id = $2`
	tag, err := r.pool.Exec(ctx, q, studyID, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// GetRole returneaza rolul unui user intr-un studiu, sau ErrNotFound daca nu e membru.
func (r *StudyMemberRepository) GetRole(ctx context.Context, studyID, userID uuid.UUID) (models.StudyRole, error) {
	const q = `SELECT role FROM study_members WHERE study_id = $1 AND user_id = $2`
	var role string
	err := r.pool.QueryRow(ctx, q, studyID, userID).Scan(&role)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	}
	if err != nil {
		return "", err
	}
	return models.StudyRole(role), nil
}

// ListForStudy returneaza membrii unui studiu cu email-urile asociate.
func (r *StudyMemberRepository) ListForStudy(ctx context.Context, studyID uuid.UUID) ([]models.StudyMember, error) {
	const q = `
		SELECT m.study_id, m.user_id, u.email, m.role, m.joined_at
		FROM study_members m
		JOIN users u ON u.id = m.user_id
		WHERE m.study_id = $1
		ORDER BY m.joined_at ASC`

	rows, err := r.pool.Query(ctx, q, studyID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []models.StudyMember
	for rows.Next() {
		var m models.StudyMember
		var role string
		if err := rows.Scan(&m.StudyID, &m.UserID, &m.Email, &role, &m.JoinedAt); err != nil {
			return nil, err
		}
		m.Role = models.StudyRole(role)
		out = append(out, m)
	}
	return out, rows.Err()
}
