package sentry

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// 가짜 DSN 수신 서버로 실제 이벤트 전송을 실측한다.
// sentry-go는 DSN에서 엔드포인트(/api/<project>/envelope/)를 유도하며,
// 본문은 envelope 형식(헤더 줄 + 아이템 줄들)이라 이벤트 JSON은 exception 키로 식별한다.
func TestCaptureErrorSendsEvent(t *testing.T) {
	t.Parallel()
	got := make(chan []byte, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		for _, line := range strings.Split(string(raw), "\n") {
			if strings.Contains(line, "exception") {
				select {
				case got <- []byte(line):
				default:
				}
				break
			}
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"1"}`))
	}))
	defer srv.Close()

	// DSN 형식: <scheme>://<publicKey>@<host>/<projectID>
	dsn := "http://pubkey@" + srv.Listener.Addr().String() + "/42"
	rep := New(dsn, "test")
	rep.CaptureError(errFake("임베딩 차원 불일치"), map[string]string{"stage": "gold"})

	select {
	case line := <-got:
		var event map[string]any
		if err := json.Unmarshal(line, &event); err != nil {
			t.Fatalf("이벤트 파싱: %v", err)
		}
		if event["environment"] != "test" {
			t.Fatalf("environment 누락: %v", event["environment"])
		}
		if event["exception"] == nil {
			t.Fatalf("exception 없음: %v", event)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("5초 내 이벤트가 전송되지 않았다")
	}

	rep.Close(2 * time.Second)
}

func TestEmptyDSNIsNoop(t *testing.T) {
	t.Parallel()
	rep := New("", "test") // 패닉 없이 Noop이어야 한다
	rep.CaptureError(errFake("x"), nil)
	rep.Close(time.Second)
}

type errFake string

func (e errFake) Error() string { return string(e) }
