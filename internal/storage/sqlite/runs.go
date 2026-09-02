package sqlite

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// Runs는 storage.RunRepo의 SQLite 구현이다.
type Runs struct {
	db *sql.DB
}

func (r *Runs) Start(ctx context.Context, at time.Time) (int64, error) {
	res, err := r.db.ExecContext(ctx,
		"INSERT INTO pipeline_runs (started_at) VALUES (?)", fmtTime(at))
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

func (r *Runs) Finish(ctx context.Context, id int64, scraped, silverUpserted, embedded int64, status string, errMsg *string, at time.Time) error {
	_, err := r.db.ExecContext(ctx, `
		UPDATE pipeline_runs
		SET finished_at = ?, scraped = ?, silver_upserted = ?, embedded = ?, status = ?, error = ?
		WHERE id = ?`, fmtTime(at), scraped, silverUpserted, embedded, status, errMsg, id)
	return err
}

const runColumns = `id, status, started_at, finished_at, scraped, silver_upserted, embedded, error`

func scanRun(scan func(dest ...any) error) (domain.RunRow, error) {
	var r domain.RunRow
	err := scan(&r.ID, &r.Status, &r.StartedAt, &r.FinishedAt,
		&r.Scraped, &r.SilverUpserted, &r.Embedded, &r.Error)
	return r, err
}

func (r *Runs) List(ctx context.Context, limit int) ([]domain.RunRow, error) {
	rows, err := r.db.QueryContext(ctx,
		"SELECT "+runColumns+" FROM pipeline_runs ORDER BY id DESC LIMIT ?", limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.RunRow{}
	for rows.Next() {
		run, err := scanRun(rows.Scan)
		if err != nil {
			return nil, err
		}
		out = append(out, run)
	}
	return out, rows.Err()
}

func (r *Runs) Latest(ctx context.Context) (*domain.RunRow, error) {
	row := r.db.QueryRowContext(ctx,
		"SELECT "+runColumns+" FROM pipeline_runs ORDER BY id DESC LIMIT 1")
	run, err := scanRun(row.Scan)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &run, nil
}

func (r *Runs) HasRunning(ctx context.Context) (bool, error) {
	var id int64
	err := r.db.QueryRowContext(ctx,
		"SELECT id FROM pipeline_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1").Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}
