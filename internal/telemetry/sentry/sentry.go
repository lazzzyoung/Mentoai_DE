// Package sentry는 telemetry.Reporter의 Sentry 참조 구현이다.
// DSN이 비어 있으면 Noop과 동일하게 동작한다(전송 없음).
package sentry

import (
	"fmt"
	"log/slog"
	"time"

	sentry "github.com/getsentry/sentry-go"

	"github.com/Chae-JS/mentoai/internal/telemetry"
)

// Reporter는 telemetry.Reporter의 Sentry 구현이다.
type Reporter struct{ hub *sentry.Hub }

// New는 Sentry SDK를 초기화한다. DSN이 비어 있으면 Noop을 반환한다.
// 초기화 실패(잘못된 DSN 등)는 기동을 막지 않고 Noop으로 폴백하되 로그를 남긴다.
func New(dsn, environment string) telemetry.Reporter {
	if dsn == "" {
		return telemetry.Noop()
	}
	err := sentry.Init(sentry.ClientOptions{
		Dsn:              dsn,
		Environment:      environment,
		AttachStacktrace: true,
	})
	if err != nil {
		slog.Warn("Sentry 초기화 실패 — 에러 리포팅 비활성", "error", err)
		return telemetry.Noop()
	}
	slog.Info("Sentry 에러 리포팅 활성화", "environment", environment)
	return Reporter{hub: sentry.CurrentHub()}
}

// CaptureError는 예외를 Sentry로 전송한다. 비동기 버퍼 방식이라 호출을 막지 않는다.
func (r Reporter) CaptureError(err error, tags map[string]string) {
	if r.hub == nil || err == nil {
		return
	}
	hub := r.hub.Clone()
	for k, v := range tags {
		hub.Scope().SetTag(k, v)
	}
	hub.CaptureException(err)
}

// Close는 대기 중인 이벤트를 마저 전송한다 (서버 종료 시 호출).
func (r Reporter) Close(timeout time.Duration) {
	if r.hub == nil {
		return
	}
	if !sentry.Flush(timeout) {
		slog.Warn("Sentry 플러시 미완료", "timeout", fmt.Sprint(timeout))
	}
}
