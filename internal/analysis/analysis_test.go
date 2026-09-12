package analysis

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/storage/sqlite"
)

type testSettings struct{}

func (testSettings) GeminiModel() string { return "test-model" }

type testGenerator struct {
	calls        int
	beforeReturn func()
}

func (g *testGenerator) GenerateAnalysis(_ context.Context, prompt string) (domain.DetailedAnalysisResponse, error) {
	g.calls++
	if g.beforeReturn != nil {
		f := g.beforeReturn
		g.beforeReturn = nil
		f()
	}
	return domain.DetailedAnalysisResponse{JobTitle: prompt}, nil
}

func TestAnalysisCacheTracksInputs(t *testing.T) {
	store, err := sqlite.Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	ctx := t.Context()
	if _, err = store.ApplyMigrations(ctx); err != nil {
		t.Fatal(err)
	}
	uid, err := store.Users.Insert(ctx, "owner")
	if err != nil {
		t.Fatal(err)
	}
	setProfile := func(skills []string) {
		t.Helper()
		if err := store.Users.UpsertSpec(ctx, uid, "backend", 2, skills); err != nil {
			t.Fatal(err)
		}
	}
	setProfile([]string{"Go"})
	job := domain.SilverRow{Source: "test", SourceID: "1", FullText: "original job"}
	setJob := func() {
		t.Helper()
		if err := store.Jobs.UpsertJobs(ctx, []domain.SilverRow{job}, time.Now()); err != nil {
			t.Fatal(err)
		}
	}
	setJob()
	jobs, err := store.Jobs.List(ctx, "", 1)
	if err != nil || len(jobs) != 1 {
		t.Fatalf("jobs: %v %v", jobs, err)
	}
	jid := jobs[0].ID
	gen := &testGenerator{}
	service := New(store.Users, store.Jobs, store.Cache, gen, testSettings{})
	analyze := func(wantCalls int) {
		t.Helper()
		if _, err := service.Analyze(ctx, jid, uid); err != nil {
			t.Fatal(err)
		}
		if gen.calls != wantCalls {
			t.Fatalf("calls=%d want=%d", gen.calls, wantCalls)
		}
	}
	// Legacy rows have no input fingerprint and must be regenerated once.
	if err := store.Cache.Upsert(ctx, jid, uid, "test-model", []byte(`{"job_title":"legacy"}`)); err != nil {
		t.Fatal(err)
	}
	analyze(1)
	analyze(1)
	setProfile([]string{"Go", "SQL"})
	analyze(2)
	analyze(2)
	job.FullText = "changed requirements"
	setJob()
	analyze(3)
	analyze(3)
	title := "new title"
	job.Position = &title
	setJob()
	analyze(4)
	// A response finishing after a profile edit must not poison the next request.
	setProfile([]string{"Python"})
	gen.beforeReturn = func() { setProfile([]string{"Rust"}) }
	analyze(5)
	analyze(6)
	analyze(6)
}
