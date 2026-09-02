// Package telemetry은 에러 리포팅의 포트를 정의한다.
// 구현은 하위 패키지(telemetry/sentry)가 공급하고, 설정이 없으면 Noop으로 동작한다.
package telemetry

import "time"

// Reporter는 애플리케이션 에러를 외부 모니터링 서비스로 보내는 포트다.
type Reporter interface {
	// CaptureError는 오류와 함께 태그(예: stage, path)를 전송한다.
	CaptureError(err error, tags map[string]string)
	// Close는 전송 대기 중인 이벤트를 마저 보내고 종료한다.
	Close(timeout time.Duration)
}

// Noop은 아무것도 하지 않는 기본 구현이다 (SENTRY_DSN 미설정 시).
type noop struct{}

func Noop() Reporter { return noop{} }

func (noop) CaptureError(error, map[string]string) {}
func (noop) Close(time.Duration)                   {}
