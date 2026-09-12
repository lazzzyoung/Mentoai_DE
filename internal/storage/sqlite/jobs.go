package sqlite

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// Jobs는 storage.JobRepo의 SQLite 구현이다.
type Jobs struct {
	db *sql.DB
}

const jobColumns = `source, source_id, company, position, location, intro, main_tasks,
	requirements, preferred_points, benefits, employment_type, is_newbie,
	annual_from, annual_to, due_time, skill_tags, pay, link, deadline,
	full_text, collected_at`

// UpsertJobs는 정제 공고를 한 트랜잭션으로 upsert한다.
// updated_at은 신규 또는 임베딩 입력(full_text) 변경 시에만 호출자의 시각을 사용한다.
func (j *Jobs) UpsertJobs(ctx context.Context, rows []domain.SilverRow, updatedAt time.Time) error {
	tx, err := j.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.PrepareContext(ctx, `
		INSERT INTO silver_jobs (`+jobColumns+`, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT (source, source_id) DO UPDATE SET
			company = excluded.company,
			position = excluded.position,
			location = excluded.location,
			intro = excluded.intro,
			main_tasks = excluded.main_tasks,
			requirements = excluded.requirements,
			preferred_points = excluded.preferred_points,
			benefits = excluded.benefits,
			employment_type = excluded.employment_type,
			is_newbie = excluded.is_newbie,
			annual_from = excluded.annual_from,
			annual_to = excluded.annual_to,
			due_time = excluded.due_time,
			skill_tags = excluded.skill_tags,
			pay = excluded.pay,
			link = excluded.link,
			deadline = excluded.deadline,
			full_text = excluded.full_text,
			collected_at = excluded.collected_at,
			updated_at = CASE
				WHEN silver_jobs.full_text IS NOT excluded.full_text THEN excluded.updated_at
				ELSE silver_jobs.updated_at END`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	updated := fmtTime(updatedAt)
	for _, r := range rows {
		skillTags, err := encodeStrings(r.SkillTags)
		if err != nil {
			return err
		}
		if _, err := stmt.ExecContext(ctx,
			r.Source, r.SourceID,
			r.Company, r.Position, r.Location, r.Intro, r.MainTasks, r.Requirements,
			r.PreferredPoint, r.Benefits, r.EmploymentType, r.IsNewbie,
			r.AnnualFrom, r.AnnualTo, r.DueTime, skillTags, r.Pay, r.Link, r.Deadline,
			r.FullText, r.CollectedAt, updated,
		); err != nil {
			return fmt.Errorf("silver upsert 실패 (%s/%s): %w", r.Source, r.SourceID, err)
		}
	}
	return tx.Commit()
}

const jobMetaSelect = `id, source, company, position, skill_tags, annual_from, annual_to, is_newbie, location`

func scanJobMeta(scan func(dest ...any) error) (domain.JobMeta, error) {
	var m domain.JobMeta
	var skillTags string
	err := scan(&m.ID, &m.Source, &m.Company, &m.Position, &skillTags,
		&m.AnnualFrom, &m.AnnualTo, &m.IsNewbie, &m.Location)
	if err != nil {
		return m, err
	}
	m.SkillTags, err = decodeStrings(skillTags)
	return m, err
}

// GetMetaByIDs는 추천 하이드레이션용 메타데이터를 id → 행 맵으로 돌려준다.
func (j *Jobs) GetMetaByIDs(ctx context.Context, ids []int64) (map[int64]domain.JobMeta, error) {
	out := make(map[int64]domain.JobMeta, len(ids))
	for _, id := range ids {
		row := j.db.QueryRowContext(ctx,
			"SELECT "+jobMetaSelect+" FROM silver_jobs WHERE id = ?", id)
		m, err := scanJobMeta(row.Scan)
		if errors.Is(err, sql.ErrNoRows) {
			continue // 검색 인덱스에 남아있는 삭제된 공고는 건너뛴다
		}
		if err != nil {
			return nil, err
		}
		out[id] = m
	}
	return out, nil
}

func (j *Jobs) GetFull(ctx context.Context, jobID int64) (*domain.JobFull, error) {
	var f domain.JobFull
	err := j.db.QueryRowContext(ctx,
		"SELECT id, company, position, full_text FROM silver_jobs WHERE id = ?", jobID).
		Scan(&f.ID, &f.Company, &f.Position, &f.FullText)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &f, nil
}

func (j *Jobs) List(ctx context.Context, query string, limit int) ([]domain.JobAdminRow, error) {
	const cols = `id, source, source_id, company, position, skill_tags, updated_at`
	base := func(where string) string {
		return "SELECT " + cols + " FROM silver_jobs" + where + " ORDER BY updated_at DESC LIMIT ?"
	}

	var (
		rows *sql.Rows
		err  error
	)
	if query != "" {
		rows, err = j.db.QueryContext(ctx, base(" WHERE company LIKE ? OR position LIKE ?"),
			"%"+query+"%", "%"+query+"%", limit)
	} else {
		rows, err = j.db.QueryContext(ctx, base(""), limit)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.JobAdminRow{}
	for rows.Next() {
		var r domain.JobAdminRow
		var skillTags string
		if err := rows.Scan(&r.ID, &r.Source, &r.SourceID, &r.Company, &r.Position, &skillTags, &r.UpdatedAt); err != nil {
			return nil, err
		}
		r.SkillTags, err = decodeStrings(skillTags)
		if err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

func (j *Jobs) GetKey(ctx context.Context, jobID int64) (*domain.JobKey, error) {
	var k domain.JobKey
	err := j.db.QueryRowContext(ctx,
		"SELECT source, source_id, company, position FROM silver_jobs WHERE id = ?", jobID).
		Scan(&k.Source, &k.SourceID, &k.Company, &k.Position)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &k, nil
}

// Delete는 공고를 삭제한다. 임베딩/캐시는 FK cascade로 함께 지워진다.
func (j *Jobs) Delete(ctx context.Context, jobID int64) (int64, error) {
	res, err := j.db.ExecContext(ctx, "DELETE FROM silver_jobs WHERE id = ?", jobID)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

func (j *Jobs) Count(ctx context.Context) (int64, error) {
	var n int64
	err := j.db.QueryRowContext(ctx, "SELECT count(*) FROM silver_jobs").Scan(&n)
	return n, err
}
