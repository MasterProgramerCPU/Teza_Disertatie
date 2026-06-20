package repository

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/tudorgeana/emedicine-api/internal/models"
)

type UserRepository struct {
	pool *pgxpool.Pool
}

func NewUserRepository(pool *pgxpool.Pool) *UserRepository {
	return &UserRepository{pool: pool}
}

func (r *UserRepository) Create(ctx context.Context, email, passwordHash string) (*models.User, error) {
	const q = `
		INSERT INTO users (email, password_hash)
		VALUES ($1, $2)
		RETURNING id, email, password_hash, is_super_admin, created_at`

	var u models.User
	err := r.pool.QueryRow(ctx, q, email, passwordHash).Scan(
		&u.ID, &u.Email, &u.PasswordHash, &u.IsSuperAdmin, &u.CreatedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return nil, ErrDuplicate
		}
		return nil, err
	}
	return &u, nil
}

func (r *UserRepository) GetByEmail(ctx context.Context, email string) (*models.User, error) {
	const q = `SELECT id, email, password_hash, is_super_admin, created_at FROM users WHERE email = $1`

	var u models.User
	err := r.pool.QueryRow(ctx, q, email).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.IsSuperAdmin, &u.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UserRepository) GetByID(ctx context.Context, id uuid.UUID) (*models.User, error) {
	const q = `SELECT id, email, password_hash, is_super_admin, created_at FROM users WHERE id = $1`

	var u models.User
	err := r.pool.QueryRow(ctx, q, id).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.IsSuperAdmin, &u.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

// SetSuperAdmin actualizeaza flag-ul is_super_admin pentru un user.
func (r *UserRepository) SetSuperAdmin(ctx context.Context, id uuid.UUID, isSuperAdmin bool) error {
	const q = `UPDATE users SET is_super_admin = $1 WHERE id = $2`
	tag, err := r.pool.Exec(ctx, q, isSuperAdmin, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// CountAll returneaza nr. total de useri.
func (r *UserRepository) CountAll(ctx context.Context) (int, error) {
	var n int
	if err := r.pool.QueryRow(ctx, `SELECT COUNT(*) FROM users`).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}

// CountSuperAdmins returneaza nr. de super admini.
func (r *UserRepository) CountSuperAdmins(ctx context.Context) (int, error) {
	var n int
	if err := r.pool.QueryRow(ctx, `SELECT COUNT(*) FROM users WHERE is_super_admin = TRUE`).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}

// ListAll returneaza toti userii, utilizat de UI-ul super admin.
func (r *UserRepository) ListAll(ctx context.Context) ([]models.User, error) {
	const q = `SELECT id, email, password_hash, is_super_admin, created_at FROM users ORDER BY created_at`
	rows, err := r.pool.Query(ctx, q)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []models.User
	for rows.Next() {
		var u models.User
		if err := rows.Scan(&u.ID, &u.Email, &u.PasswordHash, &u.IsSuperAdmin, &u.CreatedAt); err != nil {
			return nil, err
		}
		users = append(users, u)
	}
	return users, rows.Err()
}

// GetProfile returneaza proiectia publica a profilului (fara binarul avatar).
func (r *UserRepository) GetProfile(ctx context.Context, id uuid.UUID) (*models.UserProfile, error) {
	const q = `
		SELECT id, email,
		       COALESCE(full_name, ''), COALESCE(affiliation, ''), COALESCE(bio, ''),
		       (avatar_data IS NOT NULL AND octet_length(avatar_data) > 0) AS has_avatar,
		       is_super_admin, created_at
		FROM users
		WHERE id = $1`

	var p models.UserProfile
	err := r.pool.QueryRow(ctx, q, id).Scan(
		&p.ID, &p.Email, &p.FullName, &p.Affiliation, &p.Bio,
		&p.HasAvatar, &p.IsSuperAdmin, &p.CreatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &p, nil
}

// UpdateProfile aplica un patch partial pe campurile editabile.
// Doar campurile non-nil din `up` sunt scrise; restul raman intacte.
func (r *UserRepository) UpdateProfile(ctx context.Context, id uuid.UUID, up models.UserProfileUpdate) error {
	const q = `
		UPDATE users SET
			full_name   = COALESCE($2, full_name),
			affiliation = COALESCE($3, affiliation),
			bio         = COALESCE($4, bio)
		WHERE id = $1`
	tag, err := r.pool.Exec(ctx, q, id, up.FullName, up.Affiliation, up.Bio)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// SetAvatar inlocuieste binarul si mime-type-ul. Lungimea trebuie validata
// inainte de apel (max ~256KB, doar image/jpeg|image/png).
func (r *UserRepository) SetAvatar(ctx context.Context, id uuid.UUID, data []byte, mime string) error {
	const q = `UPDATE users SET avatar_data = $2, avatar_mime = $3 WHERE id = $1`
	tag, err := r.pool.Exec(ctx, q, id, data, mime)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// ClearAvatar sterge avatarul. Folosit de DELETE /api/me/avatar.
func (r *UserRepository) ClearAvatar(ctx context.Context, id uuid.UUID) error {
	const q = `UPDATE users SET avatar_data = NULL, avatar_mime = NULL WHERE id = $1`
	tag, err := r.pool.Exec(ctx, q, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// GetAvatar returneaza binarul si mime-type-ul; ErrNotFound daca avatarul lipseste.
func (r *UserRepository) GetAvatar(ctx context.Context, id uuid.UUID) ([]byte, string, error) {
	const q = `SELECT avatar_data, COALESCE(avatar_mime, '') FROM users WHERE id = $1`
	var data []byte
	var mime string
	err := r.pool.QueryRow(ctx, q, id).Scan(&data, &mime)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, "", ErrNotFound
	}
	if err != nil {
		return nil, "", err
	}
	if len(data) == 0 {
		return nil, "", ErrNotFound
	}
	return data, mime, nil
}

// HasSharedStudy verifica daca a si b au cel putin un studiu in comun.
// Folosit pentru autorizarea accesului la profile altor utilizatori.
func (r *UserRepository) HasSharedStudy(ctx context.Context, a, b uuid.UUID) (bool, error) {
	if a == b {
		return true, nil
	}
	const q = `
		SELECT EXISTS (
			SELECT 1
			FROM study_members ma
			JOIN study_members mb ON ma.study_id = mb.study_id
			WHERE ma.user_id = $1 AND mb.user_id = $2
		)`
	var ok bool
	if err := r.pool.QueryRow(ctx, q, a, b).Scan(&ok); err != nil {
		return false, err
	}
	return ok, nil
}

// ListCollaboratorsByStudy returneaza, pentru fiecare studiu in care
// utilizatorul curent e membru, lista membrilor (exclusiv el).
func (r *UserRepository) ListCollaboratorsByStudy(ctx context.Context, userID uuid.UUID) ([]models.CollaboratorsByStudy, error) {
	const q = `
		WITH my AS (
			SELECT s.id, s.name, s.disease_code, s.description, s.created_by,
			       s.created_at, s.updated_at, sm.role AS my_role
			FROM studies s
			JOIN study_members sm ON sm.study_id = s.id
			WHERE sm.user_id = $1
		)
		SELECT my.id, my.name, my.disease_code, COALESCE(my.description, ''),
		       my.created_by, my.created_at, my.updated_at, my.my_role,
		       u.id, u.email,
		       COALESCE(u.full_name, ''), COALESCE(u.affiliation, ''),
		       (u.avatar_data IS NOT NULL AND octet_length(u.avatar_data) > 0),
		       sm2.role
		FROM my
		JOIN study_members sm2 ON sm2.study_id = my.id AND sm2.user_id <> $1
		JOIN users u ON u.id = sm2.user_id
		ORDER BY my.name, u.email`

	rows, err := r.pool.Query(ctx, q, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []models.CollaboratorsByStudy{}
	byStudy := map[uuid.UUID]int{}
	for rows.Next() {
		var (
			sID, createdBy, memberID uuid.UUID
			sName, sDisease, sDesc   string
			sCreatedAt, sUpdatedAt   time.Time
			myRole, memberRole       models.StudyRole
			memberEmail, memberName  string
			memberAffil              string
			memberHasAvatar          bool
		)
		if err := rows.Scan(
			&sID, &sName, &sDisease, &sDesc, &createdBy, &sCreatedAt, &sUpdatedAt, &myRole,
			&memberID, &memberEmail, &memberName, &memberAffil, &memberHasAvatar, &memberRole,
		); err != nil {
			return nil, err
		}
		idx, ok := byStudy[sID]
		if !ok {
			out = append(out, models.CollaboratorsByStudy{
				Study: models.Study{
					ID:          sID,
					Name:        sName,
					DiseaseCode: sDisease,
					Description: sDesc,
					CreatedBy:   createdBy,
					CreatedAt:   sCreatedAt,
					UpdatedAt:   sUpdatedAt,
				},
				MyRole: myRole,
			})
			idx = len(out) - 1
			byStudy[sID] = idx
		}
		out[idx].Members = append(out[idx].Members, models.CollaboratorEntry{
			UserID:      memberID,
			Email:       memberEmail,
			FullName:    memberName,
			Affiliation: memberAffil,
			HasAvatar:   memberHasAvatar,
			Role:        memberRole,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
