package sqlite

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// Users는 storage.UserRepo의 SQLite 구현이다.
type Users struct {
	db *sql.DB
}

func (u *Users) ListSummaries(ctx context.Context) ([]domain.UserSummary, error) {
	rows, err := u.db.QueryContext(ctx, `
		SELECT u.id, u.username, s.desired_job, s.career_years
		FROM users u
		JOIN user_specs s ON s.user_id = u.id
		ORDER BY u.id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.UserSummary{}
	for rows.Next() {
		var r domain.UserSummary
		if err := rows.Scan(&r.ID, &r.Username, &r.DesiredJob, &r.CareerYears); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

func (u *Users) Info(ctx context.Context, userID int64) (*domain.UserInfo, error) {
	var username, desiredJob string
	var careerYears int
	var skillsJSON string
	err := u.db.QueryRowContext(ctx, `
		SELECT u.username, s.desired_job, s.career_years, s.skills
		FROM user_specs s
		JOIN users u ON s.user_id = u.id
		WHERE s.user_id = ?`, userID).
		Scan(&username, &desiredJob, &careerYears, &skillsJSON)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	skills, err := decodeStrings(skillsJSON)
	if err != nil {
		return nil, fmt.Errorf("user_specs skills 파싱 실패: %w", err)
	}
	return &domain.UserInfo{
		Username:    username,
		DesiredJob:  desiredJob,
		CareerYears: careerYears,
		Skills:      skills,
	}, nil
}

// Insert는 사용자를 추가한다. 이미 존재하는 이름이면 (0, nil)을 반환한다.
func (u *Users) Insert(ctx context.Context, username string) (int64, error) {
	var id int64
	err := u.db.QueryRowContext(ctx,
		"INSERT INTO users (username) VALUES (?) ON CONFLICT (username) DO NOTHING RETURNING id",
		username).Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, nil // 중복
	}
	if err != nil {
		return 0, err
	}
	return id, nil
}

func (u *Users) FindByUsername(ctx context.Context, username string) (*domain.UserRow, error) {
	var row domain.UserRow
	err := u.db.QueryRowContext(ctx, "SELECT id, username FROM users WHERE username = ?", username).
		Scan(&row.ID, &row.Username)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (u *Users) GetByID(ctx context.Context, userID int64) (*domain.UserRow, error) {
	var row domain.UserRow
	err := u.db.QueryRowContext(ctx, "SELECT id, username FROM users WHERE id = ?", userID).
		Scan(&row.ID, &row.Username)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

func (u *Users) UpsertSpec(ctx context.Context, userID int64, desiredJob string, careerYears int, skills []string) error {
	skillsJSON, err := encodeStrings(skills)
	if err != nil {
		return err
	}
	_, err = u.db.ExecContext(ctx, `
		INSERT INTO user_specs (user_id, desired_job, career_years, skills)
		VALUES (?, ?, ?, ?)
		ON CONFLICT (user_id) DO UPDATE SET
			desired_job = excluded.desired_job,
			career_years = excluded.career_years,
			skills = excluded.skills`,
		userID, desiredJob, careerYears, skillsJSON)
	return err
}

func (u *Users) Delete(ctx context.Context, userID int64) (int64, error) {
	res, err := u.db.ExecContext(ctx, "DELETE FROM users WHERE id = ?", userID)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

func (u *Users) Count(ctx context.Context) (int64, error) {
	var n int64
	err := u.db.QueryRowContext(ctx, "SELECT count(*) FROM users").Scan(&n)
	return n, err
}
