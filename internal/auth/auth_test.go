package auth

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"testing/synctest"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/storage/sqlite"
)

// ---------- 세션 매니저 ----------

func TestSessionIssueVerify(t *testing.T) {
	t.Parallel()
	m := NewSessionManager("secret-key", time.Hour, false)
	token, err := m.Issue(7, "지원")
	if err != nil {
		t.Fatal(err)
	}
	claims, err := m.Verify(token)
	if err != nil {
		t.Fatal(err)
	}
	if claims.UserID != 7 || claims.Username != "지원" {
		t.Fatalf("claims: %+v", claims)
	}
}

func TestSessionRejectsTamperAndExpiry(t *testing.T) {
	t.Parallel()
	m := NewSessionManager("secret-key", time.Hour, false)
	token, _ := m.Issue(1, "u")

	// 서명 변조
	if _, err := m.Verify(token + "x"); err == nil {
		t.Fatal("변조된 토큰은 거부되어야 한다")
	}
	// 다른 키로 검증
	if _, err := NewSessionManager("other", time.Hour, false).Verify(token); err == nil {
		t.Fatal("다른 키로 서명 검증은 실패해야 한다")
	}
	// 만료
	expired := NewSessionManager("secret-key", -time.Second, false)
	expToken, _ := expired.Issue(1, "u")
	if _, err := m.Verify(expToken); err == nil {
		t.Fatal("만료 토큰은 거부되어야 한다")
	}
	// 형식 오류
	if _, err := m.Verify("not-a-token"); err == nil {
		t.Fatal("형식 오류 토큰은 거부되어야 한다")
	}
}

// TestSessionExpiryVirtualTime은 testing/synctest(Go 1.25+)의 가상 시간으로
// 만료를 검증한다. 버블 안의 time.Sleep은 실제로 기다리지 않고 즉시 흐른다 —
// 실제 시간에 의존하지 않아 항상 결정적이고 0초 만에 끝난다.
func TestSessionExpiryVirtualTime(t *testing.T) {
	t.Parallel()
	synctest.Test(t, func(t *testing.T) {
		m := NewSessionManager("secret-key", 2*time.Hour, false)
		token, err := m.Issue(1, "u")
		if err != nil {
			t.Fatal(err)
		}
		if _, err := m.Verify(token); err != nil {
			t.Fatalf("발급 직후는 유효해야 한다: %v", err)
		}

		time.Sleep(3 * time.Hour) // 버블 안에서 가상 시간이 즉시 흐른다

		if _, err := m.Verify(token); err == nil {
			t.Fatal("가상 시간 3시간 후에는 만료되어야 한다")
		}
	})
}

// FuzzSessionVerify는 임의 입력 토큰이 패닉 없이 안전하게 처리되는지 탐색한다.
// `go test -fuzz=FuzzSessionVerify -fuzztime=30s`로 심화 실행, 평소엔 시드만 돈다.
func FuzzSessionVerify(f *testing.F) {
	f.Add("abc.def")
	f.Add("")
	f.Add("eyJ1aWQiOjF9.sig")
	f.Fuzz(func(t *testing.T, token string) {
		m := NewSessionManager("fuzz-key", time.Hour, false)
		_, _ = m.Verify(token)
	})
}

func TestSessionFromRequestCookieAndBearer(t *testing.T) {
	t.Parallel()
	m := NewSessionManager("k", time.Hour, false)
	token, _ := m.Issue(5, "베어러")

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(&http.Cookie{Name: SessionCookie, Value: token})
	if claims, err := m.FromRequest(req); err != nil || claims.UserID != 5 {
		t.Fatalf("쿠키 세션: %+v %v", claims, err)
	}

	bearer := httptest.NewRequest(http.MethodGet, "/", nil)
	bearer.Header.Set("Authorization", "Bearer "+token)
	if claims, err := m.FromRequest(bearer); err != nil || claims.UserID != 5 {
		t.Fatalf("Bearer 세션: %+v %v", claims, err)
	}

	if _, err := m.FromRequest(httptest.NewRequest(http.MethodGet, "/", nil)); err == nil {
		t.Fatal("세션 없는 요청은 오류")
	}
}

// ---------- 서비스 (실제 SQLite + 가짜 공급자 통합) ----------

type fakeProvider struct {
	name     string
	enabled  bool
	redirect bool
	identity Identity
	err      error
}

func (f *fakeProvider) Name() string  { return f.name }
func (f *fakeProvider) Enabled() bool { return f.enabled }
func (f *fakeProvider) LoginURL(string) (string, bool) {
	if f.redirect {
		return "https://consent.example?state=s", true
	}
	return "", false
}
func (f *fakeProvider) Exchange(context.Context, string, string) (Identity, error) {
	return f.identity, f.err
}

func newAuthService(t *testing.T) (*Service, *sqlite.Storage) {
	t.Helper()
	store, err := sqlite.Open("file:" + t.TempDir() + "/auth.db")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { store.Close() })
	if _, err := store.ApplyMigrations(t.Context()); err != nil {
		t.Fatal(err)
	}
	sessions := NewSessionManager("test-secret", time.Hour, false)
	providers := []Provider{
		&fakeProvider{name: "google", enabled: true, redirect: true,
			identity: Identity{Provider: "google", ProviderUserID: "sub-1", Email: "user@example.com", Name: "유저"}},
		&fakeProvider{name: "toss", enabled: true,
			identity: Identity{Provider: "toss", ProviderUserID: "9912345", Name: "토스사용자"}},
	}
	return NewService(providers, sessions, store.Users, store.Identities), store
}

func TestLoginCreatesUserAndLinks(t *testing.T) {
	t.Parallel()
	svc, store := newAuthService(t)
	ctx := t.Context()

	token, user, err := svc.Login(ctx, "google", "code", "")
	if err != nil {
		t.Fatal(err)
	}
	if token == "" {
		t.Fatal("토큰이 발급되어야 한다")
	}
	if user.Username != "user" || user.DesiredJob != "미지정" {
		t.Fatalf("자동 회원가입: %+v", user)
	}

	// 신원 연결 확인
	id, err := store.Identities.FindUserID(ctx, "google", "sub-1")
	if err != nil || id == nil || *id != user.ID {
		t.Fatalf("신원 연결: %v %v", id, err)
	}

	// 재로그인: 같은 사용자
	_, user2, err := svc.Login(ctx, "google", "code2", "")
	if err != nil {
		t.Fatal(err)
	}
	if user2.ID != user.ID {
		t.Fatalf("재로그인은 동일 사용자여야 한다: %d != %d", user2.ID, user.ID)
	}
}

func TestLoginUsernameConflictGetsSuffix(t *testing.T) {
	t.Parallel()
	svc, store := newAuthService(t)
	ctx := t.Context()

	// 미리 "user"라는 이름의 사용자를 만들어 둔다
	if _, err := store.Users.Insert(ctx, "user"); err != nil {
		t.Fatal(err)
	}
	_, user, err := svc.Login(ctx, "google", "code", "")
	if err != nil {
		t.Fatal(err)
	}
	if user.Username != "user-2" {
		t.Fatalf("중복 이름은 접미사로 회피: %q", user.Username)
	}
}

func TestLoginTossUsesUserKey(t *testing.T) {
	t.Parallel()
	svc, _ := newAuthService(t)
	_, user, err := svc.Login(t.Context(), "toss", "code", "DEFAULT")
	if err != nil {
		t.Fatal(err)
	}
	if user.Username != "토스사용자" {
		t.Fatalf("토스 사용자명: %q", user.Username)
	}
}

func TestLoginDisabledProviderRejected(t *testing.T) {
	t.Parallel()
	svc, _ := newAuthService(t)
	_, _, err := svc.Login(t.Context(), "unknown", "code", "")
	if err == nil || !strings.Contains(err.Error(), "사용할 수 없는 로그인 공급자") {
		t.Fatalf("미등록/비활성 공급자 거부: %v", err)
	}
}

func TestMeAndUpdateMe(t *testing.T) {
	t.Parallel()
	svc, _ := newAuthService(t)
	ctx := t.Context()

	token, user, err := svc.Login(ctx, "toss", "code", "")
	if err != nil {
		t.Fatal(err)
	}
	claims, err := svc.sessions.Verify(token)
	if err != nil {
		t.Fatal(err)
	}

	me, err := svc.Me(ctx, claims.UserID)
	if err != nil || me.ID != user.ID {
		t.Fatalf("me: %+v %v", me, err)
	}

	updated, err := svc.UpdateMe(ctx, claims.UserID, domain.ProfileUpdate{
		DesiredJob: "데이터 엔지니어", CareerYears: 2, Skills: []string{"Python"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if updated.DesiredJob != "데이터 엔지니어" || updated.Username != user.Username {
		t.Fatalf("수정 결과: %+v", updated)
	}

	// 검증 실패 → 422
	if _, err := svc.UpdateMe(ctx, claims.UserID, domain.ProfileUpdate{DesiredJob: "", CareerYears: 99}); err == nil {
		t.Fatal("검증 실패는 오류여야 한다")
	}
	// 없는 사용자 → 404
	if _, err := svc.Me(ctx, 99999); err == nil {
		t.Fatal("없는 사용자는 404 오류여야 한다")
	}
}
