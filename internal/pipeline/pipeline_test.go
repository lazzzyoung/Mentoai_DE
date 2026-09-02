package pipeline

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/storage/sqlite"
)

type fakeEmbedder struct{ dim int }

func (f *fakeEmbedder) EmbedDocuments(_ context.Context, texts []string) ([][]float32, error) {
	out := make([][]float32, len(texts))
	for i := range texts {
		vec := make([]float32, f.dim)
		vec[0] = 1
		out[i] = vec
	}
	return out, nil
}

func (f *fakeEmbedder) EmbedQuery(context.Context, string) ([]float32, error) {
	vec := make([]float32, f.dim)
	vec[0] = 1
	return vec, nil
}
func (f *fakeEmbedder) ModelKey() string { return "fake:model" }
func (f *fakeEmbedder) Dim() int         { return f.dim }

type fakeActive struct{ e *fakeEmbedder }

func (f fakeActive) Current() EmbeddingClient { return f.e }

func okScraper(records []domain.RawRecord) Scraper {
	return func(context.Context) ([]domain.RawRecord, error) { return records, nil }
}

func failScraper() Scraper {
	return func(context.Context) ([]domain.RawRecord, error) { return nil, errors.New("소스 장애") }
}

func bronzeRecords() []domain.RawRecord {
	return []domain.RawRecord{{
		Source:      "wanted",
		SourceID:    "1",
		CollectedAt: time.Now().UTC().Format(time.RFC3339Nano),
		Payload:     []byte(`{"id": 1, "company": {"name": "A사"}, "detail": {"position": "엔지니어"}}`),
	}}
}

func TestBronzeIsolatesScraperFailure(t *testing.T) {
	t.Parallel()
	store := testStore(t)
	ctx := t.Context()
	deps := Deps{Raw: store.Raw, Scrapers: []Scraper{failScraper(), okScraper(bronzeRecords())}}

	count, err := Bronze(ctx, deps)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("한 소스 실패에도 나머지는 수집된다: %d", count)
	}
}

func TestSilverNormalizesAndStores(t *testing.T) {
	t.Parallel()
	store := testStore(t)
	ctx := t.Context()
	deps := Deps{Raw: store.Raw, Jobs: store.Jobs, Scrapers: []Scraper{okScraper(bronzeRecords())}}

	if _, err := Bronze(ctx, deps); err != nil {
		t.Fatal(err)
	}
	count, err := Silver(ctx, deps)
	if err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("silver: %d", count)
	}
	full, err := store.Jobs.GetFull(ctx, 1)
	if err != nil || full == nil || full.Company == nil || *full.Company != "A사" {
		t.Fatalf("GetFull: %+v %v", full, err)
	}
}

func TestGoldDimensionMismatch(t *testing.T) {
	t.Parallel()
	store := testStore(t)
	ctx := t.Context()
	deps := Deps{
		Raw: store.Raw, Jobs: store.Jobs, Embeds: store.Embeddings,
		Embedder: fakeActive{&fakeEmbedder{dim: 8}},
		Scrapers: []Scraper{okScraper(bronzeRecords())},
	}
	if _, err := Bronze(ctx, deps); err != nil {
		t.Fatal(err)
	}
	if _, err := Silver(ctx, deps); err != nil {
		t.Fatal(err)
	}

	// 실제 차원 8 / 기대 차원 4 → 오류
	if _, err := Gold(ctx, deps, 4); err == nil {
		t.Fatal("차원 불일치는 오류여야 한다")
	}
}

func TestRunPipelineEndToEnd(t *testing.T) {
	t.Parallel()
	store := testStore(t)
	ctx := t.Context()
	deps := Deps{
		Raw: store.Raw, Jobs: store.Jobs, Embeds: store.Embeddings, Runs: store.Runs,
		Embedder: fakeActive{&fakeEmbedder{dim: 4}},
		Scrapers: []Scraper{okScraper(bronzeRecords())},
	}

	result, err := RunPipeline(ctx, deps, store.Runs, 4)
	if err != nil {
		t.Fatal(err)
	}
	if result.Scraped != 1 || result.SilverUpserted != 1 || result.Embedded != 1 {
		t.Fatalf("파이프라인 결과: %+v", result)
	}

	// 재실행: silver 재업서트가 updated_at을 올리므로 해당 공고는 다시
	// stale이 되어 재임베딩된다 (원본 Python과 동일한 의도된 동작).
	result, err = RunPipeline(ctx, deps, store.Runs, 4)
	if err != nil {
		t.Fatal(err)
	}
	if result.Embedded != 1 {
		t.Fatalf("갱신된 공고는 재임베딩 대상: %+v", result)
	}

	// 실행 이력 성공 기록
	latest, err := store.Runs.Latest(ctx)
	if err != nil || latest == nil || latest.Status != "success" {
		t.Fatalf("latest: %+v %v", latest, err)
	}
}

func TestRunPipelineFailureRecorded(t *testing.T) {
	t.Parallel()
	store := testStore(t)
	ctx := t.Context()
	deps := Deps{
		Raw: store.Raw, Jobs: store.Jobs, Embeds: store.Embeddings, Runs: store.Runs,
		Embedder: fakeActive{&fakeEmbedder{dim: 4}},
		Scrapers: []Scraper{okScraper(bronzeRecords())},
	}
	// 실행 이력 기록이 망가진 경우 오류가 전파된다.
	if _, err := RunPipeline(ctx, deps, failingRuns{}, 4); err == nil {
		t.Fatal("이력 기록 실패는 오류로 전파되어야 한다")
	}
}

type failingRuns struct{}

func (failingRuns) Start(context.Context, time.Time) (int64, error) {
	return 0, errors.New("이력 기록 장애")
}
func (failingRuns) Finish(context.Context, int64, int64, int64, int64, string, *string, time.Time) error {
	return errors.New("이력 기록 장애")
}

func testStore(t *testing.T) *sqlite.Storage {
	t.Helper()
	store, err := sqlite.Open(filepath.Join(t.TempDir(), "pipeline.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { store.Close() })
	if _, err := store.ApplyMigrations(t.Context()); err != nil {
		t.Fatal(err)
	}
	return store
}
