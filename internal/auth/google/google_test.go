package google

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func fakeGoogle(t *testing.T, tokenStatus int, tokenBody, userinfoBody string) (*Provider, *[]url.Values) {
	t.Helper()
	var captured []url.Values
	mux := http.NewServeMux()
	mux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		captured = append(captured, r.Form)
		w.WriteHeader(tokenStatus)
		_, _ = w.Write([]byte(tokenBody))
	})
	mux.HandleFunc("/userinfo", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(userinfoBody))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	p := New(Config{
		ClientID: "cid", ClientSecret: "secret",
		RedirectURL: "http://localhost:8000/api/v1/auth/google/callback",
		AuthBaseURL: srv.URL + "/auth",
		TokenURL:    srv.URL + "/token",
		UserinfoURL: srv.URL + "/userinfo",
	})
	return p, &captured
}

func TestEnabledAndLoginURL(t *testing.T) {
	t.Parallel()
	p, _ := fakeGoogle(t, 200, `{"access_token":"t"}`, `{}`)
	if !p.Enabled() {
		t.Fatal("client id/secret이 있으면 활성")
	}
	loginURL, ok := p.LoginURL("st123")
	if !ok || !strings.Contains(loginURL, "state=st123") ||
		!strings.Contains(loginURL, "response_type=code") ||
		!strings.Contains(loginURL, "scope=openid+email+profile") {
		t.Fatalf("동의화면 URL: %s", loginURL)
	}
}

func TestExchange(t *testing.T) {
	t.Parallel()
	p, captured := fakeGoogle(t, 200,
		`{"access_token":"tok-1"}`,
		`{"sub":"sub-77","email":"dev@example.com","name":"개발자"}`)

	identity, err := p.Exchange(t.Context(), "the-code", "")
	if err != nil {
		t.Fatal(err)
	}
	if identity.Provider != "google" || identity.ProviderUserID != "sub-77" ||
		identity.Email != "dev@example.com" || identity.Name != "개발자" {
		t.Fatalf("identity: %+v", identity)
	}
	if len(*captured) != 1 {
		t.Fatalf("토큰 요청 수: %d", len(*captured))
	}
	form := (*captured)[0]
	if form.Get("code") != "the-code" || form.Get("grant_type") != "authorization_code" ||
		form.Get("client_secret") != "secret" {
		t.Fatalf("토큰 요청 폼: %v", form)
	}
}

func TestExchangeRejectsTokenError(t *testing.T) {
	t.Parallel()
	p, _ := fakeGoogle(t, 400, `{"error":"invalid_grant"}`, `{}`)
	if _, err := p.Exchange(t.Context(), "bad", ""); err == nil ||
		!strings.Contains(err.Error(), "invalid_grant") {
		t.Fatalf("토큰 교환 거부: %v", err)
	}
}
