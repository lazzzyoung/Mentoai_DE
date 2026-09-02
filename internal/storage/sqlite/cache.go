package sqlite

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// Cache는 storage.CacheRepo의 SQLite 구현이다.
type Cache struct {
	db *sql.DB
}

func (c *Cache) Get(ctx context.Context, jobID, userID int64, model string) ([]byte, bool, error) {
	var response string
	err := c.db.QueryRowContext(ctx, `
		SELECT response FROM analysis_cache
		WHERE job_id = ? AND user_id = ? AND model = ?`, jobID, userID, model).
		Scan(&response)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return []byte(response), true, nil
}

func (c *Cache) Upsert(ctx context.Context, jobID, userID int64, model string, response []byte) error {
	_, err := c.db.ExecContext(ctx, `
		INSERT INTO analysis_cache (job_id, user_id, model, response, created_at)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT (job_id, user_id, model)
		DO UPDATE SET response = excluded.response, created_at = excluded.created_at`,
		jobID, userID, model, string(response), Now())
	return err
}

func (c *Cache) List(ctx context.Context, limit int) ([]domain.CacheRow, error) {
	rows, err := c.db.QueryContext(ctx, `
		SELECT c.job_id, c.user_id, c.model, c.created_at, u.username, j.company, j.position
		FROM analysis_cache c
		JOIN users u ON u.id = c.user_id
		JOIN silver_jobs j ON j.id = c.job_id
		ORDER BY c.created_at DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.CacheRow{}
	for rows.Next() {
		var r domain.CacheRow
		if err := rows.Scan(&r.JobID, &r.UserID, &r.Model, &r.CreatedAt, &r.Username, &r.Company, &r.Position); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Clear는 전체 캐시를 지우고 삭제된 job_id 목록 길이를 반환한다.
func (c *Cache) Clear(ctx context.Context) (int64, error) {
	rows, err := c.db.QueryContext(ctx, "DELETE FROM analysis_cache RETURNING job_id")
	if err != nil {
		return 0, err
	}
	defer rows.Close()
	var deleted int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return 0, err
		}
		deleted++
	}
	return deleted, rows.Err()
}

func (c *Cache) Delete(ctx context.Context, jobID, userID int64) (int64, error) {
	res, err := c.db.ExecContext(ctx,
		"DELETE FROM analysis_cache WHERE job_id = ? AND user_id = ?", jobID, userID)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

func (c *Cache) Count(ctx context.Context) (int64, error) {
	var n int64
	err := c.db.QueryRowContext(ctx, "SELECT count(*) FROM analysis_cache").Scan(&n)
	if err != nil {
		return 0, fmt.Errorf("analysis_cache count 실패: %w", err)
	}
	return n, err
}
