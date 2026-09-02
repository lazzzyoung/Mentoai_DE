package main

import (
	"context"
	"fmt"
	"sync"

	"github.com/Chae-JS/mentoai/internal/analysis"
	"github.com/Chae-JS/mentoai/internal/api"
	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/embedding"
	embgemini "github.com/Chae-JS/mentoai/internal/embedding/gemini"
	llmgemini "github.com/Chae-JS/mentoai/internal/llm/gemini"
	"github.com/Chae-JS/mentoai/internal/ops"
	"github.com/Chae-JS/mentoai/internal/pipeline"
	"github.com/Chae-JS/mentoai/internal/recommend"
	"github.com/Chae-JS/mentoai/internal/scheduler"
	"github.com/Chae-JS/mentoai/internal/scrapers"
	"github.com/Chae-JS/mentoai/internal/storage/sqlite"
)

const envFile = ".env"

// settingsView는 서비스들이 쓰는 좁은 설정 뷰다 (인터페이스 분리).
type settingsView struct{ holder *config.Holder }

func (v settingsView) RecommendTopK() int  { return v.holder.Get().RecommendTopK }
func (v settingsView) GeminiModel() string { return v.holder.Get().GeminiModel }

// pipelineAdapter는 pipeline 함수들을 ops.PipelineRunner로 맞춘다.
type pipelineAdapter struct {
	deps pipeline.Deps
	dim  func() int
}

func (a *pipelineAdapter) RunPipeline(ctx context.Context) (domain.PipelineResult, error) {
	return pipeline.RunPipeline(ctx, a.deps, a.deps.Runs, a.dim())
}

func (a *pipelineAdapter) EmbedAll(ctx context.Context) (int, error) {
	return pipeline.Gold(ctx, a.deps, a.dim())
}

// embedderRef는 활성 임베딩 구현을 파이프라인 포트로 노출한다.
// embedding.Embedder는 pipeline.EmbeddingClient를 구조적으로 만족한다.
type embedderRef struct{ active *embedding.AtomicEmbedder }

func (r embedderRef) Current() pipeline.EmbeddingClient { return r.active.Current() }

// scheduleRef는 살아있는 스케줄러(serve) 또는 정적 계산(CLI)으로 상태를 제공한다.
type scheduleRef struct {
	mu     sync.RWMutex
	live   *scheduler.Scheduler
	holder *config.Holder
}

func (r *scheduleRef) setLive(s *scheduler.Scheduler) {
	r.mu.Lock()
	r.live = s
	r.mu.Unlock()
}

func (r *scheduleRef) Info() domain.ScheduleInfo {
	r.mu.RLock()
	live := r.live
	r.mu.RUnlock()
	return scheduler.NewInfo(r.holder.Get(), live)
}

// App는 조립 완료된 애플리케이션이다.
type App struct {
	Settings config.Settings
	Holder   *config.Holder
	Store    *sqlite.Storage
	Ops      *ops.Service
	Active   *embedding.AtomicEmbedder
	Server   *api.Server
	Schedule *scheduleRef
	Pipeline *pipelineAdapter
}

// Wire는 전체 의존성 그래프를 구성한다(composition root).
func Wire(settings config.Settings) (*App, error) {
	store, err := sqlite.Open(settings.SQLitePath)
	if err != nil {
		return nil, err
	}
	holder := config.NewHolder(settings)

	// --- 임베딩: 포트 + 레지스트리 + 참조 구현(gemini) ---
	registry := embedding.NewRegistry()
	registry.Register("gemini", embgemini.DefaultModel, embgemini.DefaultDim,
		func(s config.Settings) (embedding.Embedder, error) { return embgemini.NewFromSettings(s) })
	initial, err := registry.Build(settings.EmbeddingProvider, settings)
	if err != nil {
		_ = store.Close()
		return nil, fmt.Errorf("임베딩 구현 초기화 실패: %w", err)
	}
	active := embedding.NewAtomic(initial)

	// --- 파이프라인 ---
	deps := pipeline.Deps{
		Raw:      store.Raw,
		Jobs:     store.Jobs,
		Embeds:   store.Embeddings,
		Runs:     store.Runs,
		Embedder: embedderRef{active: active},
		Scrapers: []pipeline.Scraper{
			scrapers.NewWanted(settings).Scrape,
			scrapers.NewWork24(settings).Scrape,
		},
	}
	runner := &pipelineAdapter{deps: deps, dim: func() int { return holder.Get().EmbeddingDim }}

	// --- 서비스 ---
	views := settingsView{holder: holder}
	generator := llmgemini.New(llmgemini.Config{APIKey: settings.GoogleAPIKey, Model: settings.GeminiModel})
	rec := recommend.New(store.Users, store.Embeddings, store.Jobs, active, views)
	ana := analysis.New(store.Users, store.Jobs, store.Cache, generator, views)

	sched := &scheduleRef{holder: holder}
	opsService := ops.New(holder, store.Users, store.Raw, store.Jobs, store.Embeddings,
		store.Cache, store.Runs, store, registry, active, runner, sched)

	return &App{
		Settings: settings,
		Holder:   holder,
		Store:    store,
		Ops:      opsService,
		Active:   active,
		Server:   api.New(store.Users, rec, ana, opsService),
		Schedule: sched,
		Pipeline: runner,
	}, nil
}
