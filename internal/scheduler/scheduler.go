// Package scheduler는 파이프라인 cron 스케줄러다. SCHEDULE_ENABLED일 때만 시작한다.
package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/robfig/cron/v3"

	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
)

// RunFunc는 스케줄 시 실행할 파이프라인 함수다.
type RunFunc func(ctx context.Context) (domain.PipelineResult, error)

// slogAdapter는 slog.Logger를 cron의 Printf 로거로 맞춘다.
func slogAdapter() interface {
	Printf(string, ...any)
} {
	return printfFunc(func(format string, args ...any) {
		slog.Info(fmt.Sprintf(format, args...))
	})
}

type printfFunc func(format string, args ...any)

func (f printfFunc) Printf(format string, args ...any) { f(format, args...) }

// Scheduler는 cron 스케줄러와 현재 상태를 캡슐화한다.
type Scheduler struct {
	cron *cron.Cron
	spec string
	loc  *time.Location
	cfg  *config.Holder
}

// Start는 스케줄러를 만들고 시작한다. 비활성이면 (nil, nil)을 반환한다.
func Start(settings config.Settings, cfg *config.Holder, run RunFunc) (*Scheduler, error) {
	if !settings.ScheduleEnabled {
		return nil, nil
	}
	loc, err := time.LoadLocation(settings.ScheduleTimezone)
	if err != nil {
		return nil, fmt.Errorf("스케줄 타임존 로드 실패: %w", err)
	}
	c := cron.New(cron.WithLocation(loc), cron.WithChain(
		cron.Recover(cron.VerbosePrintfLogger(slogAdapter())),
		cron.SkipIfStillRunning(cron.VerbosePrintfLogger(slogAdapter())),
	))
	if _, err := c.AddJob(settings.ScheduleCron, cron.FuncJob(func() {
		if _, err := run(context.Background()); err != nil {
			slog.Error("스케줄 파이프라인 실패", "error", err)
		}
	})); err != nil {
		return nil, fmt.Errorf("cron 등록 실패: %w", err)
	}
	c.Start()
	slog.Info("스케줄러 시작", "cron", settings.ScheduleCron, "timezone", settings.ScheduleTimezone)
	return &Scheduler{cron: c, spec: settings.ScheduleCron, loc: loc, cfg: cfg}, nil
}

// Stop은 스케줄러를 멈춘다(실행 중 작업 완료 대기 없음).
func (s *Scheduler) Stop() {
	if s != nil && s.cron != nil {
		s.cron.Stop()
	}
}

// Info는 현재 스케줄 상태를 돌려준다. 실행 중이면 실제 다음 실행시각이다.
func (s *Scheduler) Info() domain.ScheduleInfo { return NewInfo(s.cfg.Get(), s) }

// NewInfo는 설정과 (선택적) 스케줄러로 상태를 계산한다.
func NewInfo(settings config.Settings, s *Scheduler) domain.ScheduleInfo {
	info := domain.ScheduleInfo{
		Enabled:  settings.ScheduleEnabled,
		Cron:     settings.ScheduleCron,
		Timezone: settings.ScheduleTimezone,
	}
	if !settings.ScheduleEnabled {
		return info
	}
	if s != nil && s.cron != nil {
		entries := s.cron.Entries()
		if len(entries) > 0 && !entries[0].Next.IsZero() {
			next := entries[0].Next.Format(time.RFC3339)
			info.NextRun = &next
			return info
		}
	}

	// 스케줄러가 아직 없으면 cron 명세로 다음 실행시각을 계산한다.
	loc, err := time.LoadLocation(settings.ScheduleTimezone)
	if err != nil {
		return info
	}
	schedule, err := cron.ParseStandard(settings.ScheduleCron)
	if err != nil {
		return info
	}
	next := schedule.Next(time.Now().In(loc)).Format(time.RFC3339)
	info.NextRun = &next
	return info
}

// StaticInfo는 스케줄러 없이 설정만으로 상태를 만든다(CLI용).
func StaticInfo(settings config.Settings) domain.ScheduleInfo { return NewInfo(settings, nil) }
