// Package storage는 저장소 포트(인터페이스)를 정의한다.
// 구현은 하위 패키지가 공급하며, 소비자(서비스·파이프라인)는 생성자로 주입받는다.
package storage

import (
	"context"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// UserRepo는 사용자/스펙 저장소다.
type UserRepo interface {
	ListSummaries(ctx context.Context) ([]domain.UserSummary, error)
	Info(ctx context.Context, userID int64) (*domain.UserInfo, error)
	Insert(ctx context.Context, username string) (int64, error) // 중복이면 (0, nil)
	FindByUsername(ctx context.Context, username string) (*domain.UserRow, error)
	GetByID(ctx context.Context, userID int64) (*domain.UserRow, error)
	UpsertSpec(ctx context.Context, userID int64, desiredJob string, careerYears int, skills []string) error
	Delete(ctx context.Context, userID int64) (int64, error)
	Count(ctx context.Context) (int64, error)
}

// RawPostingRepo는 bronze 원본 수집 데이터 저장소다.
type RawPostingRepo interface {
	UpsertMany(ctx context.Context, records []domain.RawRecord) error
	All(ctx context.Context) ([]domain.RawRecord, error)
	DeleteByKey(ctx context.Context, source, sourceID string) (int64, error)
	Count(ctx context.Context) (int64, error)
}

// JobRepo는 silver 정제 공고 저장소다.
type JobRepo interface {
	UpsertJobs(ctx context.Context, rows []domain.SilverRow, updatedAt time.Time) error
	GetMetaByIDs(ctx context.Context, ids []int64) (map[int64]domain.JobMeta, error)
	GetFull(ctx context.Context, jobID int64) (*domain.JobFull, error)
	List(ctx context.Context, query string, limit int) ([]domain.JobAdminRow, error)
	GetKey(ctx context.Context, jobID int64) (*domain.JobKey, error)
	Delete(ctx context.Context, jobID int64) (int64, error)
	Count(ctx context.Context) (int64, error)
}

// EmbeddingRepo는 gold 임베딩 저장소다. 구현체는 유사도 검색 방식을 스스로 책임진다.
type EmbeddingRepo interface {
	Pending(ctx context.Context, model string) ([]domain.PendingJob, error)
	UpsertMany(ctx context.Context, rows []domain.EmbeddingRow, at time.Time) error
	DeleteAll(ctx context.Context) error
	SearchTopK(ctx context.Context, query []float32, k int) ([]domain.SearchHit, error)
	Invalidate(ctx context.Context)
	Count(ctx context.Context) (int64, error)
}

// CacheRepo는 LLM 상세 분석 캐시 저장소다.
type CacheRepo interface {
	Get(ctx context.Context, jobID, userID int64, model string) ([]byte, bool, error)
	Upsert(ctx context.Context, jobID, userID int64, model string, response []byte) error
	List(ctx context.Context, limit int) ([]domain.CacheRow, error)
	Clear(ctx context.Context) (int64, error)
	Delete(ctx context.Context, jobID, userID int64) (int64, error)
	Count(ctx context.Context) (int64, error)
}

// RunRepo는 파이프라인 실행 이력 저장소다.
type RunRepo interface {
	Start(ctx context.Context, at time.Time) (int64, error)
	Finish(ctx context.Context, id int64, scraped, silverUpserted, embedded int64, status string, errMsg *string, at time.Time) error
	List(ctx context.Context, limit int) ([]domain.RunRow, error)
	Latest(ctx context.Context) (*domain.RunRow, error)
	HasRunning(ctx context.Context) (bool, error)
}

// IdentityRepo는 외부 로그인 신원(구글 sub, 토스 userKey 등)과
// 서비스 사용자의 매핑을 담당한다.
type IdentityRepo interface {
	FindUserID(ctx context.Context, provider, providerUserID string) (*int64, error)
	Link(ctx context.Context, provider, providerUserID string, userID int64) error
}

// SizeProbe는 테이블 용량 조회다. SQLite dbstat 등 구현 의존 기능을 감싼다.
type SizeProbe interface {
	TableSizes(ctx context.Context) (bronze, jobs, embeddings int64, err error)
}
