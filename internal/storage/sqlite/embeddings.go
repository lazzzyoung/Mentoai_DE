package sqlite

import (
	"context"
	"database/sql"
	"math"
	"sort"
	"sync"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/vector"
)

// Embeddings는 storage.EmbeddingRepo의 SQLite 구현이다.
//
// pgvector HNSW 대신 프로세스 메모리 인덱스를 쓴다: 전체 (job_id, 벡터)를
// 지연 로딩해 캐시하고, 코사인 전수 검색으로 top-K를 고른다. 이 서비스 규모
// (수천~수만 건)에서 쿼리당 수 ms면 충분하다. 쓰기가 있으면 캐시를 무효화한다.
type Embeddings struct {
	db *sql.DB

	mu    sync.Mutex // 캐시 적재 경합 제어
	cache entryCache // loaded=false면 미적재
}

type entryCache struct {
	loaded  bool
	entries []indexEntry
}

type indexEntry struct {
	id   int64
	vec  []float32
	norm float64 // 로드 시 계산해 캐시 — 쿼리마다 노름을 다시 계산하지 않는다
}

func newEmbeddings(db *sql.DB) *Embeddings { return &Embeddings{db: db} }

// Pending은 신규·갱신(stale)·모델 불일치 공고, 즉 재임베딩 대상을 돌려준다.
// 원본 PENDING_SQL과 동일한 조건이다.
func (e *Embeddings) Pending(ctx context.Context, model string) ([]domain.PendingJob, error) {
	rows, err := e.db.QueryContext(ctx, `
		SELECT j.id, j.full_text
		FROM silver_jobs j
		LEFT JOIN silver_job_embeddings e ON e.job_id = j.id
		WHERE e.job_id IS NULL
		   OR e.embedded_at < j.updated_at
		   OR e.model <> ?`, model)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := []domain.PendingJob{}
	for rows.Next() {
		var p domain.PendingJob
		if err := rows.Scan(&p.ID, &p.FullText); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

func (e *Embeddings) UpsertMany(ctx context.Context, rows []domain.EmbeddingRow, at time.Time) error {
	tx, err := e.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.PrepareContext(ctx, `
		INSERT INTO silver_job_embeddings (job_id, embedding, model, embedded_at)
		VALUES (?, ?, ?, ?)
		ON CONFLICT (job_id) DO UPDATE SET
			embedding = excluded.embedding,
			model = excluded.model,
			embedded_at = excluded.embedded_at`)
	if err != nil {
		return err
	}
	defer stmt.Close()

	embeddedAt := fmtTime(at)
	for _, r := range rows {
		if _, err := stmt.ExecContext(ctx, r.JobID, vector.Encode(r.Vector), r.Model, embeddedAt); err != nil {
			return err
		}
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	e.Invalidate(ctx)
	return nil
}

func (e *Embeddings) DeleteAll(ctx context.Context) error {
	if _, err := e.db.ExecContext(ctx, "DELETE FROM silver_job_embeddings"); err != nil {
		return err
	}
	e.Invalidate(ctx)
	return nil
}

// SearchTopK는 코사인 유사도 상위 k건을 유사도 내림차순으로 돌려준다.
//
// 최적화 노트: 연결 리스트 기반 top-K는 스캔 항목마다 원소 2개(원+인터페이스
// 박싱)를 할당해 GC 압력의 원천이었다(10k×1024 기준 23,490 allocs/op).
// 지금은 고정 용량 슬라이스 삽입 정렬로 할당을 상수로 낮추고, 노름은
// 로드 시 캐시해 쿼리당 부동소수점 연산도 절반으로 줄였다.
func (e *Embeddings) SearchTopK(ctx context.Context, query []float32, k int) ([]domain.SearchHit, error) {
	entries, err := e.snapshot(ctx)
	if err != nil {
		return nil, err
	}
	if k <= 0 || len(entries) == 0 {
		return nil, nil
	}

	var qnorm float64
	for _, x := range query {
		qnorm += float64(x) * float64(x)
	}
	qnorm = math.Sqrt(qnorm)

	// 상위 k는 내림차순 정렬된 슬라이스로 유지한다. 용량이 k로 고정되어
	// 스캔 루프 내 할당이 없다.
	topk := make([]domain.SearchHit, 0, k)
	for _, en := range entries {
		denom := qnorm * en.norm
		var sim float64
		if denom != 0 { // 영벡터는 vector.Cosine과 동일하게 0점 처리
			// en.vec를 query 길이로 슬라이싱해 경계검사를 제거한다 —
			// 컴파일러가 내적 루프를 자동 벡터화할 수 있게 된다.
			if len(en.vec) < len(query) {
				continue
			}
			v := en.vec[:len(query)]
			var dot float64
			for i, x := range query {
				dot += float64(x) * float64(v[i])
			}
			sim = dot / denom
		}

		// 이미 k개이고 이번 유사도가 최하위 이하면 바로 건너뛴다 (정렬 탐색 생략)
		if len(topk) == k && sim <= topk[k-1].Similarity {
			continue
		}
		// 삽입 위치: 내림차순에서 sim보다 처음 작아지는 지점
		pos := sort.Search(len(topk), func(i int) bool { return topk[i].Similarity < sim })
		if len(topk) < k {
			topk = append(topk, domain.SearchHit{})
		}
		copy(topk[pos+1:], topk[pos:])
		topk[pos] = domain.SearchHit{JobID: en.id, Similarity: sim}
	}
	return topk, nil
}

// Invalidate는 메모리 인덱스 캐시를 버린다. 공고 삭제(cascade) 등
// 저장소 외부에서 임베딩 행이 사라졌을 때도 호출해야 한다.
func (e *Embeddings) Invalidate(_ context.Context) {
	e.mu.Lock()
	e.cache = entryCache{}
	e.mu.Unlock()
}

func (e *Embeddings) snapshot(ctx context.Context) ([]indexEntry, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.cache.loaded {
		return e.cache.entries, nil
	}

	rows, err := e.db.QueryContext(ctx, "SELECT job_id, embedding FROM silver_job_embeddings")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var entries []indexEntry
	for rows.Next() {
		var id int64
		var blob []byte
		if err := rows.Scan(&id, &blob); err != nil {
			return nil, err
		}
		vec, err := vector.Decode(blob)
		if err != nil {
			return nil, err
		}
		var norm float64
		for _, x := range vec {
			norm += float64(x) * float64(x)
		}
		entries = append(entries, indexEntry{id: id, vec: vec, norm: math.Sqrt(norm)})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if entries == nil {
		entries = []indexEntry{}
	}
	e.cache = entryCache{loaded: true, entries: entries}
	return entries, nil
}

func (e *Embeddings) Count(ctx context.Context) (int64, error) {
	var n int64
	err := e.db.QueryRowContext(ctx, "SELECT count(*) FROM silver_job_embeddings").Scan(&n)
	return n, err
}
