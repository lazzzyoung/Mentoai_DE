package sqlite

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// RawPostings는 storage.RawPostingRepo의 SQLite 구현이다.
type RawPostings struct {
	db *sql.DB
}

func (r *RawPostings) UpsertMany(ctx context.Context, records []domain.RawRecord) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.PrepareContext(ctx, `
		INSERT INTO bronze_raw_postings (source, source_id, payload, first_seen_at, collected_at)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT (source, source_id)
		DO UPDATE SET payload = excluded.payload, collected_at = excluded.collected_at`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, rec := range records {
		if _, err := stmt.ExecContext(ctx,
			rec.Source, rec.SourceID, string(rec.Payload), rec.CollectedAt, rec.CollectedAt); err != nil {
			return fmt.Errorf("bronze upsert 실패 (%s/%s): %w", rec.Source, rec.SourceID, err)
		}
	}
	return tx.Commit()
}

func (r *RawPostings) All(ctx context.Context) ([]domain.RawRecord, error) {
	rows, err := r.db.QueryContext(ctx,
		"SELECT source, source_id, payload, collected_at FROM bronze_raw_postings")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.RawRecord{}
	for rows.Next() {
		var rec domain.RawRecord
		var payload string
		if err := rows.Scan(&rec.Source, &rec.SourceID, &payload, &rec.CollectedAt); err != nil {
			return nil, err
		}
		rec.Payload = []byte(payload)
		out = append(out, rec)
	}
	return out, rows.Err()
}

func (r *RawPostings) DeleteByKey(ctx context.Context, source, sourceID string) (int64, error) {
	res, err := r.db.ExecContext(ctx,
		"DELETE FROM bronze_raw_postings WHERE source = ? AND source_id = ?", source, sourceID)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

func (r *RawPostings) Count(ctx context.Context) (int64, error) {
	var n int64
	err := r.db.QueryRowContext(ctx, "SELECT count(*) FROM bronze_raw_postings").Scan(&n)
	return n, err
}

// ---------- JSON 배열 직렬화 헬퍼 (text[] 대체) ----------

func encodeStrings(v []string) (string, error) {
	if v == nil {
		v = []string{}
	}
	b, err := json.Marshal(v)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func decodeStrings(s string) ([]string, error) {
	if s == "" {
		return []string{}, nil
	}
	var out []string
	if err := json.Unmarshal([]byte(s), &out); err != nil {
		return nil, err
	}
	return out, nil
}
