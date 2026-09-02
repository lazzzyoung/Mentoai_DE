// Package pipeline은 bronze(수집) → silver(정제) → gold(임베딩) 파이프라인이다.
// 모든 의존성은 생성자로 주입받는다.
package pipeline

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/silver"
)

// Scraper는 외부 소스에서 bronze 레코드를 수집하는 함수다.
type Scraper func(ctx context.Context) ([]domain.RawRecord, error)

// Deps는 파이프라인의 주입된 의존성 묶음이다.
type Deps struct {
	Raw      RawPostingStore
	Jobs     JobStore
	Embeds   EmbeddingStore
	Runs     RunRecorder
	Embedder EmbedderProvider
	Scrapers []Scraper
	// Reporter는 실패 시 에러 리포팅이다 (nil이면 전송하지 않는다).
	Reporter ErrorReporter
}

// ErrorReporter는 에러 리포팅 포트다 (telemetry.Reporter가 구조적으로 충족).
type ErrorReporter interface {
	CaptureError(err error, tags map[string]string)
}

// 포트는 소비자가 필요한 만큼만 선언한다(인터페이스 분리).
type RawPostingStore interface {
	UpsertMany(ctx context.Context, records []domain.RawRecord) error
	All(ctx context.Context) ([]domain.RawRecord, error)
}

type JobStore interface {
	UpsertJobs(ctx context.Context, rows []domain.SilverRow, updatedAt time.Time) error
}

type EmbeddingStore interface {
	Pending(ctx context.Context, model string) ([]domain.PendingJob, error)
	UpsertMany(ctx context.Context, rows []domain.EmbeddingRow, at time.Time) error
}

// EmbedderProvider는 현재 활성 Embedder를 돌려준다(실행 중 전환 반영).
type EmbedderProvider interface {
	Current() EmbeddingClient
}

// EmbeddingClient는 파이프라인이 쓰는 임베딩 기능만 모은 좁은 인터페이스다.
type EmbeddingClient interface {
	EmbedDocuments(ctx context.Context, texts []string) ([][]float32, error)
	EmbedQuery(ctx context.Context, text string) ([]float32, error)
	ModelKey() string
	Dim() int
}

type RunRecorder interface {
	Start(ctx context.Context, at time.Time) (int64, error)
	Finish(ctx context.Context, id int64, scraped, silverUpserted, embedded int64, status string, errMsg *string, at time.Time) error
}

// ---------- Bronze ----------

// Bronze는 수집기 결과를 bronze 테이블에 upsert한다.
// 한 소스가 실패해도 나머지 소스는 계속 수집한다.
func Bronze(ctx context.Context, d Deps) (int, error) {
	var records []domain.RawRecord
	for _, scraper := range d.Scrapers {
		found, err := scraper(ctx)
		if err != nil { // 한 소스 실패가 전체 파이프라인을 죽이지 않는다
			slog.Error("scraper 실패", "error", err)
			continue
		}
		records = append(records, found...)
	}
	if len(records) == 0 {
		slog.Warn("bronze: 수집된 레코드 없음")
		return 0, nil
	}
	if err := d.Raw.UpsertMany(ctx, records); err != nil {
		return 0, err
	}
	slog.Info("bronze upsert", "건", len(records))
	return len(records), nil
}

// ---------- Silver ----------

// Silver는 bronze 전량을 정제해 silver에 upsert한다.
func Silver(ctx context.Context, d Deps) (int, error) {
	rawRecords, err := d.Raw.All(ctx)
	if err != nil {
		return 0, err
	}
	if len(rawRecords) == 0 {
		slog.Warn("silver: bronze 데이터 없음")
		return 0, nil
	}

	rows := silver.Build(rawRecords)
	if len(rows) == 0 {
		return 0, nil
	}
	if err := d.Jobs.UpsertJobs(ctx, rows, time.Now()); err != nil {
		return 0, err
	}
	slog.Info("silver upsert", "건", len(rows))
	return len(rows), nil
}

// ---------- Gold ----------

// Gold는 재임베딩 대상 공고를 임베딩해 gold에 upsert한다.
func Gold(ctx context.Context, d Deps, expectedDim int) (int, error) {
	embedder := d.Embedder.Current()
	rows, err := d.Embeds.Pending(ctx, embedder.ModelKey())
	if err != nil {
		return 0, err
	}
	if len(rows) == 0 {
		slog.Info("gold: 임베딩 대상 없음")
		return 0, nil
	}

	texts := make([]string, len(rows))
	for i, r := range rows {
		texts[i] = r.FullText
	}
	vectors, err := embedder.EmbedDocuments(ctx, texts)
	if err != nil {
		return 0, err
	}
	if len(vectors) > 0 && len(vectors[0]) != expectedDim {
		return 0, fmt.Errorf(
			"임베딩 차원 불일치: 모델 %d차원 / 컬럼 %d차원. `mentoai switch-embedding` 으로 전환하세요",
			len(vectors[0]), expectedDim)
	}

	embeddingRows := make([]domain.EmbeddingRow, len(rows))
	for i, r := range rows {
		embeddingRows[i] = domain.EmbeddingRow{JobID: r.ID, Vector: vectors[i], Model: embedder.ModelKey()}
	}
	if err := d.Embeds.UpsertMany(ctx, embeddingRows, time.Now()); err != nil {
		return 0, err
	}
	slog.Info("gold upsert", "건", len(rows))
	return len(rows), nil
}

// ---------- Runner ----------

// RunPipeline은 bronze → silver → gold 전체를 실행하고 이력을 기록한다.
func RunPipeline(ctx context.Context, d Deps, runs RunRecorder, expectedDim int) (domain.PipelineResult, error) {
	started := time.Now()
	runID, err := runs.Start(ctx, started)
	if err != nil {
		return domain.PipelineResult{}, err
	}

	result, stage, err := run(ctx, d, expectedDim)
	if err != nil {
		slog.Error("파이프라인 실패", "stage", stage, "error", err)
		if d.Reporter != nil {
			d.Reporter.CaptureError(err, map[string]string{"stage": stage})
		}
		msg := err.Error()
		if finishErr := runs.Finish(ctx, runID, 0, 0, 0, "failed", &msg, time.Now()); finishErr != nil {
			slog.Error("실행 이력 기록 실패", "error", finishErr)
		}
		return domain.PipelineResult{}, err
	}

	if err := runs.Finish(ctx, runID,
		int64(result.Scraped), int64(result.SilverUpserted), int64(result.Embedded),
		"success", nil, time.Now()); err != nil {
		return result, err
	}
	slog.Info("파이프라인 완료", "result", result)
	return result, nil
}

// run은 단계를 순서대로 실행하고 실패한 단계명을 함께 돌려준다.
func run(ctx context.Context, d Deps, expectedDim int) (result domain.PipelineResult, stage string, err error) {
	stage = "bronze"
	scraped, err := Bronze(ctx, d)
	if err != nil {
		return domain.PipelineResult{}, stage, err
	}
	stage = "silver"
	silverUpserted, err := Silver(ctx, d)
	if err != nil {
		return domain.PipelineResult{}, stage, err
	}
	stage = "gold"
	embedded, err := Gold(ctx, d, expectedDim)
	if err != nil {
		return domain.PipelineResult{}, stage, err
	}
	return domain.PipelineResult{
		Scraped:        scraped,
		SilverUpserted: silverUpserted,
		Embedded:       embedded,
	}, stage, nil
}
