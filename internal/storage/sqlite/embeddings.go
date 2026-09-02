package sqlite

import (
	"container/list"
	"context"
	"database/sql"
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
	cache entryCache // nil이면 미적재 / 빈 값이면 빈 인덱스
}

type entryCache struct {
	loaded  bool
	entries []indexEntry
}

type indexEntry struct {
	id  int64
	vec []float32
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
func (e *Embeddings) SearchTopK(ctx context.Context, query []float32, k int) ([]domain.SearchHit, error) {
	entries, err := e.snapshot(ctx)
	if err != nil {
		return nil, err
	}
	if k <= 0 || len(entries) == 0 {
		return nil, nil
	}

	// k가 작으므로 정렬 대신 상위 k 삽입 유지: O(n·k)
	type pair struct {
		id  int64
		sim float64
	}
	best := list.New() // 유사도 내림차순 유지
	for _, en := range entries {
		sim := vector.Cosine(query, en.vec)
		var prev *list.Element
		for el := best.Front(); el != nil; el = el.Next() {
			if el.Value.(pair).sim >= sim {
				prev = el
				continue
			}
			break
		}
		item := pair{id: en.id, sim: sim}
		if prev == nil {
			best.PushFront(item) // 현재까지 최댓값
		} else {
			best.InsertAfter(item, prev)
		}
		if best.Len() > k {
			best.Remove(best.Back())
		}
	}

	hits := make([]domain.SearchHit, 0, best.Len())
	for el := best.Front(); el != nil; el = el.Next() {
		p := el.Value.(pair)
		hits = append(hits, domain.SearchHit{JobID: p.id, Similarity: p.sim})
	}
	return hits, nil
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
		entries = append(entries, indexEntry{id: id, vec: vec})
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
