package sqlite

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

func newTestStore(t *testing.T) *Storage {
	t.Helper()
	store, err := Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { store.Close() })
	if _, err := store.ApplyMigrations(context.Background()); err != nil {
		t.Fatal(err)
	}
	return store
}

func seedUser(t *testing.T, store *Storage, username string) int64 {
	t.Helper()
	id, err := store.Users.Insert(context.Background(), username)
	if err != nil || id == 0 {
		t.Fatalf("사용자 삽입: id=%d err=%v", id, err)
	}
	return id
}

func TestUserCRUD(t *testing.T) {
	store := newTestStore(t)
	ctx := context.Background()

	id := seedUser(t, store, "지원")
	if err := store.Users.UpsertSpec(ctx, id, "데이터 엔지니어", 2, []string{"Python", "SQL"}); err != nil {
		t.Fatal(err)
	}

	info, err := store.Users.Info(ctx, id)
	if err != nil || info == nil {
		t.Fatalf("조회: %v %v", info, err)
	}
	if info.Username != "지원" || info.DesiredJob != "데이터 엔지니어" || len(info.Skills) != 2 {
		t.Fatalf("스펙 불일치: %+v", info)
	}

	summaries, err := store.Users.ListSummaries(ctx)
	if err != nil || len(summaries) != 1 {
		t.Fatalf("목록: %v %v", summaries, err)
	}

	// 중복 삽입은 (0, nil)
	dup, err := store.Users.Insert(ctx, "지원")
	if err != nil || dup != 0 {
		t.Fatalf("중복 삽입: %d %v", dup, err)
	}

	// 스펙 갱신
	if err := store.Users.UpsertSpec(ctx, id, "백엔드 개발자", 3, nil); err != nil {
		t.Fatal(err)
	}
	info, _ = store.Users.Info(ctx, id)
	if info.DesiredJob != "백엔드 개발자" || info.Skills == nil || len(info.Skills) != 0 {
		t.Fatalf("갱신 실패: %+v", info)
	}

	// 삭제 cascade
	affected, err := store.Users.Delete(ctx, id)
	if err != nil || affected != 1 {
		t.Fatalf("삭제: %d %v", affected, err)
	}
	if affected, _ := store.Users.Delete(ctx, id); affected != 0 {
		t.Fatal("없는 사용자 삭제는 0행")
	}
}

func TestJobUpsertAndPendingAndSearch(t *testing.T) {
	store := newTestStore(t)
	ctx := context.Background()

	from := 2
	now := time.Now()
	rows := []domain.SilverRow{
		{Source: "wanted", SourceID: "1", Company: strptr("A사"), Position: strptr("엔지니어"),
			DueTime: "상시채용", SkillTags: []string{"Go"}, FullText: "A사 엔지니어", AnnualFrom: &from},
		{Source: "wanted", SourceID: "2", Company: strptr("B사"), Position: strptr("분석가"),
			DueTime: "상시채용", FullText: "B사 분석가"},
	}
	if err := store.Jobs.UpsertJobs(ctx, rows, now); err != nil {
		t.Fatal(err)
	}
	// id는 AUTOINCREMENT라 두 번째 행이 id 2
	full, err := store.Jobs.GetFull(ctx, 2)
	if err != nil || full == nil || full.FullText != "B사 분석가" {
		t.Fatalf("GetFull: %+v %v", full, err)
	}

	// Pending: 모두 미임베딩
	pending, err := store.Embeddings.Pending(ctx, "gemini:gemini-embedding-001")
	if err != nil || len(pending) != 2 {
		t.Fatalf("pending: %d %v", len(pending), err)
	}

	// gold upsert
	at := time.Now()
	err = store.Embeddings.UpsertMany(ctx, []domain.EmbeddingRow{
		{JobID: 1, Vector: []float32{1, 0}, Model: "gemini:gemini-embedding-001"},
		{JobID: 2, Vector: []float32{0, 1}, Model: "gemini:gemini-embedding-001"},
	}, at)
	if err != nil {
		t.Fatal(err)
	}
	// Pending 소멸
	pending, _ = store.Embeddings.Pending(ctx, "gemini:gemini-embedding-001")
	if len(pending) != 0 {
		t.Fatalf("임베딩 후 pending: %d", len(pending))
	}

	// 검색: (1,0) 쿼리는 A사가 1등
	hits, err := store.Embeddings.SearchTopK(ctx, []float32{1, 0}, 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(hits) != 2 || hits[0].JobID != 1 || hits[0].Similarity < 0.999 {
		t.Fatalf("검색 결과: %+v", hits)
	}

	// 공고 갱신(updated_at 증가) → stale 감지
	if err := store.Jobs.UpsertJobs(ctx, rows[:1], now.Add(2*time.Second)); err != nil {
		t.Fatal(err)
	}
	pending, _ = store.Embeddings.Pending(ctx, "gemini:gemini-embedding-001")
	if len(pending) != 1 || pending[0].ID != 1 {
		t.Fatalf("stale 감지 실패: %+v", pending)
	}

	// 모델 불일치 감지
	pending, _ = store.Embeddings.Pending(ctx, "gemini:다른모델")
	if len(pending) != 2 {
		t.Fatalf("모델 불일치 감지 실패: %d", len(pending))
	}

	// 공고 삭제 → 임베딩/캐시 cascade + 목록 축소
	if affected, _ := store.Jobs.Delete(ctx, 1); affected != 1 {
		t.Fatal("공고 삭제 실패")
	}
	count, _ := store.Embeddings.Count(ctx)
	if count != 1 {
		t.Fatalf("cascade 실패: %d", count)
	}
}

func TestDeleteAllAndInvalidate(t *testing.T) {
	store := newTestStore(t)
	ctx := context.Background()

	rows := []domain.SilverRow{{Source: "s", SourceID: "1", DueTime: "상시채용", FullText: "x"}}
	if err := store.Jobs.UpsertJobs(ctx, rows, time.Now()); err != nil {
		t.Fatal(err)
	}
	if err := store.Embeddings.UpsertMany(ctx, []domain.EmbeddingRow{
		{JobID: 1, Vector: []float32{1, 1}, Model: "m"},
	}, time.Now()); err != nil {
		t.Fatal(err)
	}
	// 검색 인덱스 적재
	if hits, _ := store.Embeddings.SearchTopK(ctx, []float32{1, 1}, 5); len(hits) != 1 {
		t.Fatalf("검색: %+v", hits)
	}
	if err := store.Embeddings.DeleteAll(ctx); err != nil {
		t.Fatal(err)
	}
	hits, _ := store.Embeddings.SearchTopK(ctx, []float32{1, 1}, 5)
	if len(hits) != 0 {
		t.Fatalf("DeleteAll 후 캐시 무효화 실패: %+v", hits)
	}
}

func TestAnalysisCache(t *testing.T) {
	store := newTestStore(t)
	ctx := context.Background()

	userID := seedUser(t, store, "테스터")
	rows := []domain.SilverRow{{Source: "s", SourceID: "1", Company: strptr("C"), DueTime: "d", FullText: "x"}}
	if err := store.Jobs.UpsertJobs(ctx, rows, time.Now()); err != nil {
		t.Fatal(err)
	}

	if _, ok, _ := store.Cache.Get(ctx, 1, userID, "m"); ok {
		t.Fatal("캐시 미스 기대")
	}
	if err := store.Cache.Upsert(ctx, 1, userID, "m", []byte(`{"job_title":"t"}`)); err != nil {
		t.Fatal(err)
	}
	raw, ok, err := store.Cache.Get(ctx, 1, userID, "m")
	if err != nil || !ok || string(raw) != `{"job_title":"t"}` {
		t.Fatalf("캐시 히트: %s %v %v", raw, ok, err)
	}

	cacheRows, err := store.Cache.List(ctx, 20)
	if err != nil || len(cacheRows) != 1 || cacheRows[0].Username != "테스터" {
		t.Fatalf("목록: %+v %v", cacheRows, err)
	}

	deleted, err := store.Cache.Clear(ctx)
	if err != nil || deleted != 1 {
		t.Fatalf("전체 삭제: %d %v", deleted, err)
	}
}

func TestPipelineRuns(t *testing.T) {
	store := newTestStore(t)
	ctx := context.Background()

	running, err := store.Runs.HasRunning(ctx)
	if err != nil || running {
		t.Fatalf("초기 running: %v %v", running, err)
	}

	runID, err := store.Runs.Start(ctx, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if running, _ := store.Runs.HasRunning(ctx); !running {
		t.Fatal("실행 중이어야 한다")
	}

	errMsg := "boom"
	if err := store.Runs.Finish(ctx, runID, 3, 2, 1, "failed", &errMsg, time.Now()); err != nil {
		t.Fatal(err)
	}
	if running, _ := store.Runs.HasRunning(ctx); running {
		t.Fatal("완료 후 running 해제")
	}

	latest, err := store.Runs.Latest(ctx)
	if err != nil || latest == nil || latest.Status != "failed" || latest.Error == nil || *latest.Error != "boom" {
		t.Fatalf("latest: %+v %v", latest, err)
	}
	if latest.Scraped == nil || *latest.Scraped != 3 {
		t.Fatalf("scraped: %v", latest.Scraped)
	}
}

func TestListJobsQueryFilter(t *testing.T) {
	store := newTestStore(t)
	ctx := context.Background()

	rows := []domain.SilverRow{
		{Source: "s", SourceID: "1", Company: strptr("멘토AI"), Position: strptr("엔지니어"), DueTime: "d"},
		{Source: "s", SourceID: "2", Company: strptr("다른회사"), Position: strptr("디자이너"), DueTime: "d"},
	}
	if err := store.Jobs.UpsertJobs(ctx, rows, time.Now()); err != nil {
		t.Fatal(err)
	}

	all, err := store.Jobs.List(ctx, "", 30)
	if err != nil || len(all) != 2 {
		t.Fatalf("전체 목록: %d %v", len(all), err)
	}
	filtered, err := store.Jobs.List(ctx, "멘토", 30)
	if err != nil || len(filtered) != 1 || *filtered[0].Company != "멘토AI" {
		t.Fatalf("검색: %+v %v", filtered, err)
	}
}

func strptr(s string) *string { return &s }
