package toss

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func fakeToss(t *testing.T, tokenStatus int, tokenBody, meBody string) (*Provider, *[]generateTokenRequest) {
	t.Helper()
	var captured []generateTokenRequest
	mux := http.NewServeMux()
	mux.HandleFunc("/api-partner/v1/apps-in-toss/user/oauth2/generate-token", func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		var body generateTokenRequest
		_ = json.Unmarshal(raw, &body)
		captured = append(captured, body)
		w.WriteHeader(tokenStatus)
		_, _ = w.Write([]byte(tokenBody))
	})
	mux.HandleFunc("/api-partner/v1/apps-in-toss/user/oauth2/login-me", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer toss-token" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		_, _ = w.Write([]byte(meBody))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	// mTLS 클라이언트 대신 평문 테스트 클라이언트를 주입한다.
	p, err := New(Config{BaseURL: srv.URL, HTTPClient: srv.Client()})
	if err != nil {
		t.Fatal(err)
	}
	return p, &captured
}

func TestExchange(t *testing.T) {
	t.Parallel()
	p, captured := fakeToss(t, 200,
		`{"tokenType":"bearer","accessToken":"toss-token","expiresIn":3600}`,
		`{"userKey":9876543210,"scope":"profile"}`)

	identity, err := p.Exchange(t.Context(), "auth-code-1", "DEFAULT")
	if err != nil {
		t.Fatal(err)
	}
	if identity.Provider != "toss" || identity.ProviderUserID != "9876543210" {
		t.Fatalf("identity: %+v", identity)
	}
	if len(*captured) != 1 || (*captured)[0].AuthorizationCode != "auth-code-1" ||
		(*captured)[0].Referrer != "DEFAULT" {
		t.Fatalf("generate-token 요청: %+v", *captured)
	}
}

func TestExchangeRejectsInvalidGrant(t *testing.T) {
	t.Parallel()
	p, _ := fakeToss(t, 200, `{"error":"invalid_grant"}`, `{}`)
	// access_token이 빈 경우 → 거부
	_, err := p.Exchange(t.Context(), "expired", "")
	if err == nil || !strings.Contains(err.Error(), "invalid_grant") {
		t.Fatalf("인가 코드 만료/재사용은 거부: %v", err)
	}
}

func TestLoginURLNotSupported(t *testing.T) {
	t.Parallel()
	p, _ := fakeToss(t, 200, `{}`, `{}`)
	if _, ok := p.LoginURL("s"); ok {
		t.Fatal("토스는 redirect 방식이 아니다 (클라이언트 SDK가 인가 코드 수령)")
	}
}

func TestNewWithoutCertIsDisabled(t *testing.T) {
	t.Parallel()
	p, err := New(Config{})
	if err != nil {
		t.Fatal(err)
	}
	if p.Enabled() {
		t.Fatal("인증서 없으면 비활성")
	}
}
