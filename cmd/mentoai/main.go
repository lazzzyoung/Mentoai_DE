// MentoAI — Go + SQLite 단일 스택 커리어 로드맵 서비스.
// 단일 바이너리로 API 서버와 파이프라인 CLI를 모두 제공한다.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"
	// 컨테이너(distrolress 등)에서도 Asia/Seoul 타임존이 동작하도록 tzdata를 포함한다.
	_ "time/tzdata"

	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/pipeline"
	"github.com/Chae-JS/mentoai/internal/scheduler"
	"github.com/Chae-JS/mentoai/internal/storage/sqlite"
)

func main() {
	setupLogging()
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	var err error
	switch os.Args[1] {
	case "serve":
		err = cmdServe(os.Args[2:])
	case "migrate":
		err = cmdMigrate()
	case "seed":
		err = cmdSeed()
	case "scrape":
		err = cmdScrape()
	case "transform":
		err = cmdTransform()
	case "embed":
		err = cmdEmbed(os.Args[2:])
	case "pipeline":
		err = cmdPipeline()
	case "status":
		err = cmdStatus()
	case "models":
		err = cmdModels()
	case "switch-embedding":
		err = cmdSwitchEmbedding(os.Args[2:])
	case "jobs":
		err = cmdJobs(os.Args[2:])
	case "users":
		err = cmdUsers(os.Args[2:])
	case "help", "-h", "--help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "알 수 없는 명령: %s\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}
	if err != nil {
		if httpErr := asHTTP(err); httpErr != nil {
			fmt.Fprintln(os.Stderr, httpErr.Detail)
		} else {
			fmt.Fprintln(os.Stderr, err)
		}
		os.Exit(1)
	}
}

func usage() {
	fmt.Print(`MentoAI 파이프라인 CLI

Usage:
  mentoai <command> [flags]

Commands:
  serve             API 서버 실행 (시작 시 마이그레이션 자동 적용)
  migrate           migrations/*.sql 을 DB에 적용한다
  seed              샘플 사용자/스펙을 적재한다 (멱등)
  scrape            Bronze: 공고 수집 → bronze_raw_postings upsert
  transform         Silver: bronze → 통합 스키마 정제 → silver_jobs upsert
  embed             Gold: 정제 공고 임베딩 → silver_job_embeddings upsert
  pipeline          bronze → silver → gold 전체 파이프라인 실행
  status            DB 현황·모델·스케줄·최근 실행 요약
  models            사용 가능한 임베딩 provider 목록과 현재 선택
  switch-embedding  임베딩 모델 전환: .env 갱신 + 전량 재임베딩
  jobs list|rm      공고 데이터 관리
  users list|set|rm 인재 관리
`)
}

func asHTTP(err error) *domain.HTTPError {
	var he *domain.HTTPError
	if errors.As(err, &he) {
		return he
	}
	return nil
}

// ---------- serve ----------

func cmdServe(args []string) error {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	host := fs.String("host", "0.0.0.0", "바인딩 호스트")
	port := fs.Int("port", 8000, "포트")
	_ = fs.Parse(args)

	settings := config.Load(envFile)
	if err := os.MkdirAll(dirOf(settings.SQLitePath), 0o755); err != nil {
		return err
	}
	app, err := Wire(settings)
	if err != nil {
		return err
	}
	defer app.Store.Close()

	ctx := context.Background()
	applied, err := app.Store.ApplyMigrations(ctx)
	if err != nil {
		return fmt.Errorf("마이그레이션 실패: %w", err)
	}
	if len(applied) > 0 {
		slog.Info("migration applied", "files", strings.Join(applied, ", "))
	}
	if settings.SeedOnStart {
		if err := seedUsers(ctx, app.Store); err != nil {
			return fmt.Errorf("시드 실패: %w", err)
		}
		slog.Info("시드 완료 (SEED_ON_START=true)")
	}

	sched, err := scheduler.Start(settings, app.Holder, func(ctx context.Context) (domain.PipelineResult, error) {
		return app.Pipeline.RunPipeline(ctx)
	})
	if err != nil {
		return err
	}
	if sched != nil {
		app.Schedule.setLive(sched)
		defer sched.Stop()
	}

	srv := &http.Server{
		Addr:    fmt.Sprintf("%s:%d", *host, *port),
		Handler: app.Server.Handler(),
		// 타임아웃: 느린 클라이언트(slowloris)·죽은 연결이 고루틴과 메모리를
		// 누수시키지 않게 한다. 내부 프록시(Caddy) 뒤에서도 무해한 값.
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	go func() {
		slog.Info("MentoAI 서버 시작", "addr", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("서버 오류", "error", err)
			os.Exit(1)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop
	slog.Info("종료 신호 수신 — 서버를 닫는다")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	err = srv.Shutdown(shutdownCtx)
	app.Reporter.Close(5 * time.Second) // 대기 중인 에러 이벤트 마저 전송
	return err
}

func dirOf(path string) string {
	if idx := strings.LastIndexAny(path, "/\\"); idx > 0 {
		return path[:idx]
	}
	return "."
}

// ---------- 파이프라인 ----------

// wireMinimal은 기본 .env로 앱을 조립한다.
func wireMinimal() (*App, error) { return Wire(config.Load(envFile)) }

// wireMinimalWithEnv는 지정한 .env로 앱을 조립한다.
func wireMinimalWithEnv(path string) (*App, error) { return Wire(config.Load(path)) }

func cmdMigrate() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	applied, err := app.Store.ApplyMigrations(context.Background())
	if err != nil {
		return err
	}
	if len(applied) > 0 {
		fmt.Printf("적용된 마이그레이션: %s\n", strings.Join(applied, ", "))
	} else {
		fmt.Println("적용할 마이그레이션 없음 (최신 상태)")
	}
	return nil
}

var sampleUsers = []struct {
	username    string
	desiredJob  string
	careerYears int
	skills      []string
}{
	{"지원", "데이터 엔지니어", 2, []string{"Python", "SQL", "Airflow", "Spark"}},
	{"하늘", "데이터 분석가", 1, []string{"Python", "SQL", "Tableau"}},
	{"도윤", "백엔드 개발자", 3, []string{"Java", "Spring", "AWS", "Docker"}},
}

func cmdSeed() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	if err := seedUsers(context.Background(), app.Store); err != nil {
		return err
	}
	fmt.Printf("시드 완료: 사용자 %d명\n", len(sampleUsers))
	return nil
}

// seedUsers는 샘플 사용자/스펙을 멱등 upsert한다 (CLI seed와 SEED_ON_START 공용).
func seedUsers(ctx context.Context, store *sqlite.Storage) error {
	for _, u := range sampleUsers {
		id, err := store.Users.Insert(ctx, u.username)
		if err != nil {
			return err
		}
		if id == 0 {
			row, err := store.Users.FindByUsername(ctx, u.username)
			if err != nil {
				return err
			}
			if row == nil {
				return fmt.Errorf("시드 실패: 사용자 %s를 찾을 수 없음", u.username)
			}
			id = row.ID
		}
		if err := store.Users.UpsertSpec(ctx, id, u.desiredJob, u.careerYears, u.skills); err != nil {
			return err
		}
	}
	return nil
}

func cmdScrape() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	count, err := pipeline.Bronze(context.Background(), app.Pipeline.deps)
	if err != nil {
		return err
	}
	fmt.Printf("bronze 수집: %d건\n", count)
	return nil
}

func cmdTransform() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	count, err := pipeline.Silver(context.Background(), app.Pipeline.deps)
	if err != nil {
		return err
	}
	fmt.Printf("silver 적재: %d건\n", count)
	return nil
}

func cmdEmbed(args []string) error {
	fset := flag.NewFlagSet("embed", flag.ExitOnError)
	force := fset.Bool("force", false, "기존 임베딩 전량 삭제 후 재계산")
	_ = fset.Parse(args)

	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	ctx := context.Background()
	var count int
	if *force {
		count, err = app.Ops.RebuildEmbeddings(ctx)
	} else {
		count, err = app.Pipeline.EmbedAll(ctx)
	}
	if err != nil {
		return err
	}
	suffix := ""
	if *force {
		suffix = " (전량 재계산)"
	}
	fmt.Printf("gold 임베딩: %d건%s\n", count, suffix)
	return nil
}

func cmdPipeline() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	result, err := app.Pipeline.RunPipeline(context.Background())
	if err != nil {
		return err
	}
	raw, _ := json.Marshal(result)
	fmt.Println(string(raw))
	return nil
}

// ---------- 현황 ----------

func cmdStatus() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	result, err := app.Ops.Status(context.Background())
	if err != nil {
		return err
	}

	nextRun := "-"
	if result.Schedule.NextRun != nil {
		nextRun = *result.Schedule.NextRun
	}
	enabled := "꺼짐"
	if result.Schedule.Enabled {
		enabled = "켜짐"
	}
	fmt.Printf("임베딩: %s (%d차원)\n", result.EmbeddingModel, result.EmbeddingDim)
	fmt.Printf("LLM: %s\n", result.GeminiModel)
	fmt.Printf("데이터: 브론즈 %d건 / 공고 %d건 / 임베딩 %d건 / 인재 %d명 / 캐시 %d건\n",
		result.Bronze, result.Jobs, result.Embeddings, result.Users, result.CachedAnalyses)
	fmt.Printf("용량: bronze %s ㅣ jobs %s ㅣ embeddings %s\n",
		result.Sizes.BronzeSize, result.Sizes.JobsSize, result.Sizes.EmbeddingsSize)
	fmt.Printf("스케줄: %s (%s) → 다음 %s\n", enabled, result.Schedule.Cron, nextRun)
	if len(result.Running) > 0 {
		fmt.Printf("실행 중 작업: %s\n", strings.Join(result.Running, ", "))
	}
	if result.LastRun != nil {
		scraped := int64(0)
		if result.LastRun.Scraped != nil {
			scraped = *result.LastRun.Scraped
		}
		fmt.Printf("최근 파이프라인: #%d %s (수집 %d)\n", result.LastRun.ID, result.LastRun.Status, scraped)
	}
	return nil
}

// ---------- 모델 관리 ----------

func cmdModels() error {
	app, err := wireMinimal()
	if err != nil {
		return err
	}
	defer app.Store.Close()
	info := app.Ops.EmbeddingModels()
	fmt.Printf("현재 선택: %s\n\n", info.Current)
	fmt.Println("등록된 임베딩 provider:")
	for _, m := range info.Available {
		fmt.Printf("  %-12s model=%s dim=%d\n", m.Provider, m.Model, m.Dim)
	}
	fmt.Printf("\nAPI 옵션: EMBEDDING_PROVIDER=gemini (%s)\n", info.GeminiDefault)
	return nil
}

func cmdSwitchEmbedding(args []string) error {
	fset := flag.NewFlagSet("switch-embedding", flag.ExitOnError)
	provider := fset.String("provider", "", "provider (gemini)")
	model := fset.String("model", "", "모델명 (생략 시 기본값)")
	dim := fset.Int("dim", 0, "차원 (생략 시 기본값)")
	envPath := fset.String("env-file", envFile, "갱신할 .env 경로")
	yes := fset.Bool("yes", false, "확인 프롬프트 생략")
	_ = fset.Parse(args)
	if *provider == "" {
		return errors.New("--provider는 필수입니다")
	}

	app, err := wireMinimalWithEnv(*envPath)
	if err != nil {
		return err
	}
	defer app.Store.Close()

	var dimPtr *int
	if *dim != 0 {
		dimPtr = dim
	}
	target, err := app.Ops.ResolveEmbeddingTarget(*provider, *model, dimPtr)
	if err != nil {
		return err
	}
	fmt.Printf("전환 대상: provider=%s, model=%s, dim=%d\n", target.Provider, target.Model, target.Dim)
	fmt.Println("기존 임베딩은 모두 재계산되고 .env는 .env.bak으로 백업됩니다.")
	if !*yes && !confirm("계속할까요?") {
		fmt.Println("중단했습니다.")
		return nil
	}

	result, err := app.Ops.SwitchEmbeddingModel(context.Background(), *provider, *model, dimPtr)
	if err != nil {
		return err
	}
	fmt.Printf("전환 완료: %s:%s (%d차원), 재임베딩 %d건\n",
		result.Provider, result.Model, result.Dim, result.ReEmbedded)
	return nil
}

func confirm(prompt string) bool {
	fmt.Printf("%s [y/N] ", prompt)
	reader := bufio.NewReader(os.Stdin)
	line, _ := reader.ReadString('\n')
	line = strings.ToLower(strings.TrimSpace(line))
	return line == "y" || line == "yes"
}

// ---------- 공고 관리 ----------

func cmdJobs(args []string) error {
	if len(args) == 0 {
		usage()
		os.Exit(2)
	}
	switch args[0] {
	case "list":
		fset := flag.NewFlagSet("jobs list", flag.ExitOnError)
		query := fset.String("query", "", "회사명·포지션 검색")
		fset.StringVar(query, "q", "", "회사명·포지션 검색 (축약)")
		limit := fset.Int("limit", 30, "조회 건수")
		fset.IntVar(limit, "n", 30, "조회 건수 (축약)")
		_ = fset.Parse(args[1:])

		app, err := wireMinimal()
		if err != nil {
			return err
		}
		defer app.Store.Close()
		rows, err := app.Ops.ListJobs(context.Background(), *query, *limit)
		if err != nil {
			return err
		}
		if len(rows) == 0 {
			fmt.Println("조회 결과 없음")
			return nil
		}
		for _, j := range rows {
			fmt.Printf("  %4d  [%s] %s ㅣ %s\n", j.ID, j.Source, nilOr(j.Company, "-"), nilOr(j.Position, "-"))
		}
		return nil
	case "rm":
		if len(args) < 2 {
			return errors.New("사용법: mentoai jobs rm JOB_ID")
		}
		jobID, err := strconv.ParseInt(args[1], 10, 64)
		if err != nil {
			return fmt.Errorf("공고 ID는 정수여야 합니다: %s", args[1])
		}
		app, err := wireMinimal()
		if err != nil {
			return err
		}
		defer app.Store.Close()
		key, err := app.Store.Jobs.GetKey(context.Background(), jobID)
		if err != nil {
			return err
		}
		if key == nil {
			fmt.Printf("삭제 실패: 공고 없음: %d\n", jobID)
			os.Exit(1)
		}
		if err := app.Ops.DeleteJob(context.Background(), jobID); err != nil {
			return err
		}
		fmt.Printf("삭제 완료: #%d %s %s\n", jobID, nilOr(key.Company, "-"), nilOr(key.Position, "-"))
		return nil
	default:
		fmt.Fprintf(os.Stderr, "알 수 없는 하위 명령: jobs %s\n", args[0])
		os.Exit(2)
	}
	return nil
}

// ---------- 인재 관리 ----------

func cmdUsers(args []string) error {
	if len(args) == 0 {
		usage()
		os.Exit(2)
	}
	switch args[0] {
	case "list":
		app, err := wireMinimal()
		if err != nil {
			return err
		}
		defer app.Store.Close()
		rows, err := app.Store.Users.ListSummaries(context.Background())
		if err != nil {
			return err
		}
		for _, u := range rows {
			fmt.Printf("  %3d  %s ㅣ %s ㅣ 경력 %d년\n", u.ID, u.Username, u.DesiredJob, u.CareerYears)
		}
		return nil
	case "set":
		// flag 패키지는 positional 뒤의 플래그를 못 읽으므로 직접 분리한다.
		positional, rest := splitPositional(args[1:], map[string]bool{
			"--job": true, "--years": true, "--skills": true,
		})
		fset := flag.NewFlagSet("users set", flag.ExitOnError)
		job := fset.String("job", "", "희망 직무")
		years := fset.Int("years", 0, "경력(년)")
		skills := fset.String("skills", "", "보유 스킬 (콤마 구분)")
		_ = fset.Parse(rest)
		var username string
		if len(positional) > 0 {
			username = positional[0]
		}
		if username == "" || *job == "" {
			return errors.New("사용법: mentoai users set USERNAME --job 직무 [--years N] [--skills a,b,c]")
		}

		app, err := wireMinimal()
		if err != nil {
			return err
		}
		defer app.Store.Close()
		ctx := context.Background()

		var parsedSkills []string
		for _, s := range strings.Split(*skills, ",") {
			if trimmed := strings.TrimSpace(s); trimmed != "" {
				parsedSkills = append(parsedSkills, trimmed)
			}
		}
		payload := domain.UserPayload{
			Username: username, DesiredJob: *job, CareerYears: *years, Skills: parsedSkills,
		}
		result, err := app.Ops.CreateUser(ctx, payload)
		if httpErr := asHTTP(err); httpErr != nil && httpErr.Code == 409 {
			existing, findErr := app.Ops.FindUserByName(ctx, payload.Username)
			if findErr != nil {
				return findErr
			}
			if existing == nil {
				return fmt.Errorf("사용자를 찾을 수 없음: %s", payload.Username)
			}
			result, err = app.Ops.UpdateUser(ctx, existing.ID, payload)
		}
		if err != nil {
			return err
		}
		fmt.Printf("저장 완료: #%d %s ㅣ %s ㅣ 경력 %d년\n",
			result.ID, result.Username, result.DesiredJob, result.CareerYears)
		return nil
	case "rm":
		if len(args) < 2 {
			return errors.New("사용법: mentoai users rm ID_또는_이름")
		}
		identifier := args[1]
		app, err := wireMinimal()
		if err != nil {
			return err
		}
		defer app.Store.Close()
		ctx := context.Background()

		var userID int64
		if id, parseErr := strconv.ParseInt(identifier, 10, 64); parseErr == nil {
			userID = id
		} else {
			existing, findErr := app.Ops.FindUserByName(ctx, identifier)
			if findErr != nil {
				return findErr
			}
			if existing == nil {
				fmt.Printf("삭제 실패: 사용자 없음: %s\n", identifier)
				os.Exit(1)
			}
			userID = existing.ID
		}
		if err := app.Ops.DeleteUser(ctx, userID); err != nil {
			if httpErr := asHTTP(err); httpErr != nil {
				fmt.Printf("삭제 실패: %s\n", httpErr.Detail)
				os.Exit(1)
			}
			return err
		}
		fmt.Printf("삭제 완료: #%d\n", userID)
		return nil
	default:
		fmt.Fprintf(os.Stderr, "알 수 없는 하위 명령: users %s\n", args[0])
		os.Exit(2)
	}
	return nil
}

func nilOr(s *string, def string) string {
	if s == nil || *s == "" {
		return def
	}
	return *s
}

// splitPositional은 플래그와 위치 인자를 섞여 있어도 분리한다.
// valueKnown: 값을 갖는 플래그 이름 집합 (해당 플래그 뒤 토큰을 값으로 흡수).
func splitPositional(args []string, valueKnown map[string]bool) (flags, positional []string) {
	for i := 0; i < len(args); i++ {
		tok := args[i]
		if strings.HasPrefix(tok, "-") && tok != "-" {
			flags = append(flags, tok)
			// --flag=value 형태가 아니고 값을 갖는 플래그면 다음 토큰을 흡수한다.
			if valueKnown[tok] && !strings.Contains(tok, "=") && i+1 < len(args) {
				i++
				flags = append(flags, args[i])
			}
			continue
		}
		positional = append(positional, tok)
	}
	return flags, positional
}

func setupLogging() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))
}
