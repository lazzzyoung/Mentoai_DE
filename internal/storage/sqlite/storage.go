// Package sqlite는 storage 포트의 SQLite 구현과 마이그레이션 러너를 제공한다.
package sqlite

import (
	"context"
	"database/sql"
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

// Storage는 SQLite 기반 구현체다. 각 필드가 storage 포트를 구현하며,
// 소비자에는 인터페이스로 주입된다.
type Storage struct {
	DB         *sql.DB
	Users      *Users
	Raw        *RawPostings
	Jobs       *Jobs
	Embeddings *Embeddings
	Cache      *Cache
	Runs       *Runs
	Identities *Identities
}

// Open은 SQLite 파일을 열고 PRAGMA를 설정한다. :memory:는 테스트용 임시 DB다.
func Open(path string) (*Storage, error) {
	dsn := dsnFor(path)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("sqlite open 실패: %w", err)
	}
	// 동시 쓰기 직렬화: busy_timeout과 WAL로 충분하다.
	db.SetMaxOpenConns(4)
	if err := ping(db); err != nil {
		db.Close()
		return nil, err
	}
	s := &Storage{
		DB:         db,
		Users:      &Users{db: db},
		Raw:        &RawPostings{db: db},
		Jobs:       &Jobs{db: db},
		Embeddings: newEmbeddings(db),
		Cache:      &Cache{db: db},
		Runs:       &Runs{db: db},
		Identities: &Identities{db: db},
	}
	return s, nil
}

func dsnFor(path string) string {
	if strings.Contains(path, ":memory:") || strings.Contains(path, "file:") {
		return path
	}
	// _pragma 옵션은 modernc.org/sqlite 전용 DSN 파라미터다.
	return path + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(1)"
}

func ping(db *sql.DB) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	return db.PingContext(ctx)
}

// Close는 연결을 닫는다.
func (s *Storage) Close() error { return s.DB.Close() }

// ApplyMigrations는 migrations/*.sql을 파일명 순서대로 한 번씩만 적용한다.
func (s *Storage) ApplyMigrations(ctx context.Context) ([]string, error) {
	entries, err := fs.ReadDir(migrationsFS, "migrations")
	if err != nil {
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".sql") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)

	if _, err := s.DB.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TEXT NOT NULL
		)`); err != nil {
		return nil, err
	}

	done := map[string]struct{}{}
	rows, err := s.DB.QueryContext(ctx, "SELECT version FROM schema_migrations")
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var v string
		if err := rows.Scan(&v); err != nil {
			rows.Close()
			return nil, err
		}
		done[v] = struct{}{}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	var applied []string
	for _, name := range names {
		if _, ok := done[name]; ok {
			continue
		}
		body, err := migrationsFS.ReadFile("migrations/" + name)
		if err != nil {
			return nil, err
		}
		tx, err := s.DB.BeginTx(ctx, nil)
		if err != nil {
			return nil, err
		}
		if _, err := tx.ExecContext(ctx, string(body)); err != nil {
			tx.Rollback()
			return nil, fmt.Errorf("migration %s 적용 실패: %w", name, err)
		}
		if _, err := tx.ExecContext(ctx,
			"INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
			name, Now()); err != nil {
			tx.Rollback()
			return nil, err
		}
		if err := tx.Commit(); err != nil {
			return nil, err
		}
		applied = append(applied, name)
	}
	return applied, nil
}

// TableSizes는 dbstat 가상 테이블로 테이블 바이트 수를 조회한다.
// dbstat을 쓸 수 없으면 오류를 반환하고 호출자가 우아하게 표기만 한다.
func (s *Storage) TableSizes(ctx context.Context) (bronze, jobs, embeddings int64, err error) {
	for _, t := range []struct {
		name string
		out  *int64
	}{
		{"bronze_raw_postings", &bronze},
		{"silver_jobs", &jobs},
		{"silver_job_embeddings", &embeddings},
	} {
		err = s.DB.QueryRowContext(ctx,
			"SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name = ?", t.name).Scan(t.out)
		if err != nil {
			return 0, 0, 0, err
		}
	}
	return bronze, jobs, embeddings, nil
}

// timeLayout은 고정폭 나노초 UTC 포맷이다. 자릿수가 고정되어 있어
// 문자열 비교가 곧 시간 비교가 된다 (RFC3339Nano는 후행 0을 잘라 비교가 깨진다).
const timeLayout = "2006-01-02T15:04:05.000000000Z"

// Now는 저장 계층 표준 타임스탬프를 만든다.
func Now() string { return time.Now().UTC().Format(timeLayout) }

// fmtTime은 time.Time을 저장용 문자열로 바꾼다.
func fmtTime(t time.Time) string { return t.UTC().Format(timeLayout) }

// parseTime은 저장된 문자열을 time.Time으로 복원한다.
func parseTime(s string) (time.Time, error) { return time.Parse(timeLayout, s) }
