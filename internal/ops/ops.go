// Package ops는 CLI와 어드민 API가 공유하는 운영 작업 계층이다.
// 한 곳에 구현해 두 인터페이스가 항상 같은 로직을 돌린다.
package ops

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"sort"
	"strconv"
	"sync"

	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/embedding"
	"github.com/Chae-JS/mentoai/internal/envfile"
	"github.com/Chae-JS/mentoai/internal/storage"
)

// PipelineRunner는 파이프라인 실행 어댑터다 (composition root에서 조립).
type PipelineRunner interface {
	// RunPipeline은 bronze→silver→gold 전체를 실행한다.
	RunPipeline(ctx context.Context) (domain.PipelineResult, error)
	// EmbedAll은 gold(임베딩)만 실행한다.
	EmbedAll(ctx context.Context) (int, error)
}

// ScheduleInfoProvider는 스케줄 상태를 돌려준다 (스케줄러가 구현).
type ScheduleInfoProvider interface {
	Info() domain.ScheduleInfo
}

// Service는 운영 서비스다.
type Service struct {
	cfg      *config.Holder
	users    storage.UserRepo
	raw      storage.RawPostingRepo
	jobs     storage.JobRepo
	embeds   storage.EmbeddingRepo
	cache    storage.CacheRepo
	runs     storage.RunRepo
	probe    storage.SizeProbe
	registry *embedding.Registry
	active   *embedding.AtomicEmbedder
	runner   PipelineRunner
	schedule ScheduleInfoProvider
	guard    *Guard
}

// New는 의존성을 주입받아 운영 서비스를 만든다.
func New(
	cfg *config.Holder,
	users storage.UserRepo,
	raw storage.RawPostingRepo,
	jobs storage.JobRepo,
	embeds storage.EmbeddingRepo,
	cache storage.CacheRepo,
	runs storage.RunRepo,
	probe storage.SizeProbe,
	registry *embedding.Registry,
	active *embedding.AtomicEmbedder,
	runner PipelineRunner,
	schedule ScheduleInfoProvider,
	reporter ErrorReporter,
) *Service {
	return &Service{
		cfg: cfg, users: users, raw: raw, jobs: jobs, embeds: embeds,
		cache: cache, runs: runs, probe: probe, registry: registry,
		active: active, runner: runner, schedule: schedule, guard: NewGuard(reporter),
	}
}

// ---------- 백그라운드 작업 가드 ----------

// ErrorReporter는 에러 리포팅 포트다 (telemetry.Reporter가 구조적으로 충족).
type ErrorReporter interface {
	CaptureError(err error, tags map[string]string)
}

// Guard는 이름 기반 단일 실행 가드다. Python의 start_background와 동일한 의미다.
type Guard struct {
	mu       sync.Mutex
	running  map[string]struct{}
	reporter ErrorReporter
}

func NewGuard(reporter ErrorReporter) *Guard {
	return &Guard{running: map[string]struct{}{}, reporter: reporter}
}

// Start는 동일 이름 작업이 이미 돌면 false를 반환하고, 아니면 고루틴으로 실행한다.
func (g *Guard) Start(name string, fn func(ctx context.Context) error) bool {
	g.mu.Lock()
	if _, dup := g.running[name]; dup {
		g.mu.Unlock()
		return false
	}
	g.running[name] = struct{}{}
	g.mu.Unlock()

	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("백그라운드 작업 패닉", "op", name, "panic", r)
				if g.reporter != nil {
					g.reporter.CaptureError(fmt.Errorf("백그라운드 작업 패닉 (%s): %v", name, r),
						map[string]string{"op": name, "kind": "panic"})
				}
			}
			g.mu.Lock()
			delete(g.running, name)
			g.mu.Unlock()
		}()
		if err := fn(context.Background()); err != nil {
			slog.Error("백그라운드 작업 실패", "op", name, "error", err)
			if g.reporter != nil {
				g.reporter.CaptureError(err, map[string]string{"op": name})
			}
		}
	}()
	return true
}

// Running은 실행 중 작업 이름을 정렬해 돌려준다.
func (g *Guard) Running() []string {
	g.mu.Lock()
	defer g.mu.Unlock()
	out := make([]string, 0, len(g.running))
	for name := range g.running {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

// ---------- 현황 ----------

// Status는 대시보드 현황을 집계한다.
func (s *Service) Status(ctx context.Context) (domain.Status, error) {
	var out domain.Status
	bronze, err := s.raw.Count(ctx)
	if err != nil {
		return out, err
	}
	jobs, err := s.jobs.Count(ctx)
	if err != nil {
		return out, err
	}
	embeds, err := s.embeds.Count(ctx)
	if err != nil {
		return out, err
	}
	users, err := s.users.Count(ctx)
	if err != nil {
		return out, err
	}
	cached, err := s.cache.Count(ctx)
	if err != nil {
		return out, err
	}
	lastRun, err := s.runs.Latest(ctx)
	if err != nil {
		return out, err
	}

	settings := s.cfg.Get()
	out = domain.Status{
		Bronze:         bronze,
		Jobs:           jobs,
		Embeddings:     embeds,
		Users:          users,
		CachedAnalyses: cached,
		Sizes:          s.sizes(ctx),
		EmbeddingModel: s.active.Current().ModelKey(),
		EmbeddingDim:   settings.EmbeddingDim,
		GeminiModel:    settings.GeminiModel,
		Schedule:       s.schedule.Info(),
		Running:        s.guard.Running(),
		LastRun:        lastRun,
	}
	if out.Running == nil {
		out.Running = []string{}
	}
	return out, nil
}

// sizes는 테이블 용량을 사람이 읽는 형태로 조회한다. dbstat 미지원 시 "-"다.
func (s *Service) sizes(ctx context.Context) domain.Sizes {
	out := domain.Sizes{BronzeSize: "-", JobsSize: "-", EmbeddingsSize: "-"}
	bronze, jobs, embeds, err := s.probe.TableSizes(ctx)
	if err != nil {
		return out
	}
	out.BronzeSize = prettyBytes(bronze)
	out.JobsSize = prettyBytes(jobs)
	out.EmbeddingsSize = prettyBytes(embeds)
	return out
}

// prettyBytes는 pg_size_pretty 비슷한 표기를 만든다.
func prettyBytes(n int64) string {
	const unit = 1024
	if n < unit {
		return fmt.Sprintf("%d bytes", n)
	}
	value := float64(n)
	for _, suffix := range []string{"kB", "MB", "GB", "TB"} {
		value /= unit
		if value < unit {
			return fmt.Sprintf("%.1f %s", value, suffix)
		}
	}
	return fmt.Sprintf("%.1f PB", value/unit)
}

// ListRuns는 최근 파이프라인 실행 이력을 돌려준다.
func (s *Service) ListRuns(ctx context.Context, limit int) ([]domain.RunRow, error) {
	rows, err := s.runs.List(ctx, clamp(limit, 20))
	return rows, err
}

// ---------- 공고 ----------

// ListJobs는 회사명·포지션 검색으로 공고 목록을 돌려준다.
func (s *Service) ListJobs(ctx context.Context, query string, limit int) ([]domain.JobAdminRow, error) {
	return s.jobs.List(ctx, query, clamp(limit, 30))
}

// DeleteJob은 silver 공고와 대응하는 bronze 원본까지 지운다 (임베딩/캐시는 cascade).
func (s *Service) DeleteJob(ctx context.Context, jobID int64) error {
	key, err := s.jobs.GetKey(ctx, jobID)
	if err != nil {
		return err
	}
	if key == nil {
		return domain.NotFound(fmt.Sprintf("공고 없음: %d", jobID))
	}
	if _, err := s.jobs.Delete(ctx, jobID); err != nil {
		return err
	}
	if _, err := s.raw.DeleteByKey(ctx, key.Source, key.SourceID); err != nil {
		return err
	}
	// cascade로 사라진 임베딩 행이 검색 인덱스 캐시에 남지 않게 한다.
	s.embeds.Invalidate(ctx)
	slog.Info("공고 삭제", "id", jobID)
	return nil
}

// ---------- 인재 ----------

// CreateUser는 사용자와 스펙을 등록한다. 중복 이름은 409 오류다.
func (s *Service) CreateUser(ctx context.Context, p domain.UserPayload) (domain.UserResponse, error) {
	var out domain.UserResponse
	if err := p.Validate(); err != nil {
		return out, domain.Unprocessable(err.Error())
	}
	id, err := s.users.Insert(ctx, p.Username)
	if err != nil {
		return out, err
	}
	if id == 0 {
		return out, domain.Conflict(fmt.Sprintf("이미 존재하는 사용자: %s", p.Username))
	}
	if err := s.users.UpsertSpec(ctx, id, p.DesiredJob, p.CareerYears, p.Skills); err != nil {
		return out, err
	}
	return toUserResponse(id, p), nil
}

// UpdateUser는 사용자 스펙을 갱신한다. 사용자가 없으면 404다.
func (s *Service) UpdateUser(ctx context.Context, userID int64, p domain.UserPayload) (domain.UserResponse, error) {
	var out domain.UserResponse
	if err := p.Validate(); err != nil {
		return out, domain.Unprocessable(err.Error())
	}
	row, err := s.users.GetByID(ctx, userID)
	if err != nil {
		return out, err
	}
	if row == nil {
		return out, domain.NotFound(fmt.Sprintf("사용자 없음: %d", userID))
	}
	if err := s.users.UpsertSpec(ctx, userID, p.DesiredJob, p.CareerYears, p.Skills); err != nil {
		return out, err
	}
	return toUserResponse(userID, p), nil
}

func toUserResponse(id int64, p domain.UserPayload) domain.UserResponse {
	skills := p.Skills
	if skills == nil {
		skills = []string{}
	}
	return domain.UserResponse{
		ID: id, Username: p.Username, DesiredJob: p.DesiredJob,
		CareerYears: p.CareerYears, Skills: skills,
	}
}

// FindUserByName은 이름으로 사용자를 찾는다.
func (s *Service) FindUserByName(ctx context.Context, username string) (*domain.UserRow, error) {
	return s.users.FindByUsername(ctx, username)
}

// DeleteUser는 사용자를 삭제한다(관련 캐시 cascade).
func (s *Service) DeleteUser(ctx context.Context, userID int64) error {
	affected, err := s.users.Delete(ctx, userID)
	if err != nil {
		return err
	}
	if affected == 0 {
		return domain.NotFound(fmt.Sprintf("사용자 없음: %d", userID))
	}
	return nil
}

// ---------- 임베딩 ----------

// RebuildEmbeddings는 전량 재계산한다. 임베딩은 파생 데이터라 전체 삭제 후 재적재한다.
func (s *Service) RebuildEmbeddings(ctx context.Context) (int, error) {
	if err := s.embeds.DeleteAll(ctx); err != nil {
		return 0, err
	}
	return s.runner.EmbedAll(ctx)
}

// EmbeddingModels는 현재 선택과 등록된 공급자 목록을 돌려준다.
func (s *Service) EmbeddingModels() domain.EmbeddingModels {
	settings := s.cfg.Get()
	return domain.EmbeddingModels{
		Current:       s.active.Current().ModelKey(),
		Provider:      settings.EmbeddingProvider,
		Dim:           settings.EmbeddingDim,
		Available:     s.registry.Models(),
		GeminiDefault: "gemini-embedding-001",
	}
}

// ResolveEmbeddingTarget은 전환 대상을 검증만 수행한다(실제 전환 전 400 응답용).
func (s *Service) ResolveEmbeddingTarget(providerName, model string, dim *int) (domain.Target, error) {
	target, err := s.registry.Resolve(providerName, model, dim)
	if err != nil {
		return domain.Target{}, domain.BadRequest(err.Error())
	}
	return target, nil
}

// SwitchEmbeddingModel은 .env 갱신 → 설정·구현체 교체 → 전량 재임베딩을 수행한다.
func (s *Service) SwitchEmbeddingModel(ctx context.Context, providerName, model string, dim *int) (domain.SwitchResult, error) {
	var result domain.SwitchResult

	target, err := s.registry.Resolve(providerName, model, dim)
	if err != nil {
		return result, domain.BadRequest(err.Error())
	}
	settings := s.cfg.Get()

	// Gemini 전환 시 API 키 사전 확인 (환경변수 또는 기존 .env)
	if providerName == "gemini" && os.Getenv("GOOGLE_API_KEY") == "" &&
		!envfile.HasKey(settings.EnvFile, "GOOGLE_API_KEY") {
		return result, domain.BadRequest("GOOGLE_API_KEY가 없습니다. .env에 먼저 설정하세요")
	}

	// .env 갱신(주석 보존 + 백업) 후 프로세스 설정도 즉시 동기화
	updates := map[string]string{
		"EMBEDDING_PROVIDER":     target.Provider,
		"EMBEDDING_DIM":          strconv.Itoa(target.Dim),
		"EMBEDDING_MODEL":        settings.EmbeddingModel,
		"GEMINI_EMBEDDING_MODEL": settings.GeminiEmbeddingModel,
	}
	if target.Provider == "gemini" {
		updates["GEMINI_EMBEDDING_MODEL"] = target.Model
	} else {
		updates["EMBEDDING_MODEL"] = target.Model
	}
	backup, err := envfile.Update(settings.EnvFile, updates)
	if err != nil {
		return result, err
	}
	for key, value := range updates {
		if err := os.Setenv(key, value); err != nil {
			return result, err
		}
	}
	newSettings := settings
	newSettings.EmbeddingProvider = target.Provider
	newSettings.EmbeddingDim = target.Dim
	newSettings.EmbeddingModel = updates["EMBEDDING_MODEL"]
	newSettings.GeminiEmbeddingModel = updates["GEMINI_EMBEDDING_MODEL"]
	s.cfg.Set(newSettings)

	// 임베딩은 파생 데이터: 전량 삭제 후 새 구현체로 재임베딩
	newEmbedder, err := s.registry.Build(target.Provider, newSettings)
	if err != nil {
		return result, err
	}
	s.active.Swap(newEmbedder)

	if err := s.embeds.DeleteAll(ctx); err != nil {
		return result, err
	}
	reEmbedded, err := s.runner.EmbedAll(ctx)
	if err != nil {
		return result, err
	}

	result = domain.SwitchResult{
		Provider: target.Provider, Model: target.Model, Dim: target.Dim,
		ReEmbedded: reEmbedded, EnvBackup: backup,
	}
	slog.Info("임베딩 모델 전환 완료", "provider", result.Provider, "model", result.Model)
	return result, nil
}

// ---------- 캐시 ----------

// ListCache는 최근 분석 캐시 20건을 돌려준다.
func (s *Service) ListCache(ctx context.Context) ([]domain.CacheRow, error) {
	return s.cache.List(ctx, 20)
}

// ClearCache는 전체 캐시를 지우고 건수를 반환한다.
func (s *Service) ClearCache(ctx context.Context) (int64, error) {
	return s.cache.Clear(ctx)
}

// DeleteCache는 특정 (공고, 사용자) 캐시를 지운다.
func (s *Service) DeleteCache(ctx context.Context, jobID, userID int64) error {
	affected, err := s.cache.Delete(ctx, jobID, userID)
	if err != nil {
		return err
	}
	if affected == 0 {
		return domain.NotFound(fmt.Sprintf("캐시 없음: job=%d user=%d", jobID, userID))
	}
	return nil
}

// ---------- 백그라운드 트리거 ----------

// TriggerPipeline은 파이프라인을 백그라운드로 즉시 실행한다.
// 실행 중 파이프라인이 있거나(409) 가드에 걸리면(409) 오류다.
func (s *Service) TriggerPipeline(ctx context.Context) error {
	running, err := s.runs.HasRunning(ctx)
	if err != nil {
		return err
	}
	if running {
		return domain.Conflict("파이프라인이 이미 실행 중입니다")
	}
	if !s.guard.Start("pipeline", func(bg context.Context) error {
		slog.Info("어드민 요청으로 파이프라인 즉시 실행")
		_, err := s.runner.RunPipeline(bg)
		return err
	}) {
		return domain.Conflict("동일 작업이 이미 실행 중입니다")
	}
	return nil
}

// StartBackground는 이름 기반 가드로 임의 작업을 실행한다 (어드민 임베딩 작업용).
func (s *Service) StartBackground(name string, fn func(ctx context.Context) error) bool {
	return s.guard.Start(name, fn)
}

// RunningOps는 실행 중 작업 목록이다.
func (s *Service) RunningOps() []string { return s.guard.Running() }

func clamp(v, def int) int {
	if v < 1 {
		v = 1
	}
	if v > 100 {
		v = 100
	}
	return v
}
