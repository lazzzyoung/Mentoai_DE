package sqlite

import (
	"context"
	"fmt"
	"path/filepath"
	"testing"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// SearchTopK 벤치마크: 공고 1만 건(1024차원) 기준으로
// 시간은 물론 요청당 할당(allocs/op)도 함께 본다 — GC 압력의 원천이기 때문.

func benchStore(b *testing.B, jobs, dim int) *Storage {
	b.Helper()
	store, err := Open(filepath.Join(b.TempDir(), "bench.db"))
	if err != nil {
		b.Fatal(err)
	}
	b.Cleanup(func() { store.Close() })
	ctx := context.Background()
	if _, err := store.ApplyMigrations(ctx); err != nil {
		b.Fatal(err)
	}

	rows := make([]domain.SilverRow, jobs)
	for i := range rows {
		rows[i] = domain.SilverRow{
			Source: "bench", SourceID: fmt.Sprint(i), DueTime: "d", FullText: "x",
		}
	}
	if err := store.Jobs.UpsertJobs(ctx, rows, time.Now()); err != nil {
		b.Fatal(err)
	}
	embeddings := make([]domain.EmbeddingRow, jobs)
	for i := range embeddings {
		vec := make([]float32, dim)
		for d := range vec {
			vec[d] = float32(i%7) + float32(d)/float32(dim)
		}
		embeddings[i] = domain.EmbeddingRow{JobID: int64(i + 1), Vector: vec, Model: "bench"}
	}
	if err := store.Embeddings.UpsertMany(ctx, embeddings, time.Now()); err != nil {
		b.Fatal(err)
	}
	return store
}

func BenchmarkSearchTopK10k(b *testing.B) {
	store := benchStore(b, 10_000, 1024)
	ctx := context.Background()
	query := make([]float32, 1024)
	for d := range query {
		query[d] = 0.5
	}

	b.ReportAllocs()
	b.ResetTimer()

	// 인덱스 최초 로드(10k행 디코드)는 측정에서 제외한다 — 검색의 안정 상태 성능이다.
	if _, err := store.Embeddings.SearchTopK(ctx, query, 5); err != nil {
		b.Fatal(err)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		hits, err := store.Embeddings.SearchTopK(ctx, query, 5)
		if err != nil || len(hits) != 5 {
			b.Fatalf("hits=%d err=%v", len(hits), err)
		}
	}
}
