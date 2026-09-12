package api

import (
	"github.com/Chae-JS/mentoai/internal/auth"
	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/storage/sqlite"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"
)

func TestAuthorizationBoundaries(t *testing.T) {
	adminRoutes := []struct{ method, path string }{
		{"GET", "/api/v1/admin/stats"}, {"GET", "/api/v1/admin/pipeline-runs"},
		{"POST", "/api/v1/admin/pipeline"}, {"GET", "/api/v1/admin/jobs"},
		{"DELETE", "/api/v1/admin/jobs/1"}, {"POST", "/api/v1/admin/users"},
		{"PUT", "/api/v1/admin/users/1"}, {"DELETE", "/api/v1/admin/users/1"},
		{"GET", "/api/v1/admin/embedding/models"}, {"POST", "/api/v1/admin/embedding/rebuild"},
		{"POST", "/api/v1/admin/embedding/switch"}, {"GET", "/api/v1/admin/cache"},
		{"DELETE", "/api/v1/admin/cache"}, {"DELETE", "/api/v1/admin/cache/1/1"},
	}
	for _, loggedIn := range []bool{false, true} {
		auth := &fakeAuth{authenticated: loggedIn, meUser: domain.UserResponse{ID: 42}}
		// nil downstream services prove denied requests cannot reach the operation.
		srv := New(nil, nil, nil, nil, auth, true, &fakeReporter{}, 99)
		for _, route := range adminRoutes {
			w := httptest.NewRecorder()
			srv.Handler().ServeHTTP(w, httptest.NewRequest(route.method, route.path, nil))
			want := 401
			if loggedIn {
				want = 403
			}
			if w.Code != want {
				t.Fatalf("%s %s loggedIn=%v: %d want %d", route.method, route.path, loggedIn, w.Code, want)
			}
		}
	}
	for _, path := range []string{"/api/v1/jobs/recommend/1", "/api/v1/jobs/recommend/0001", "/api/v1/jobs/2/analyze/1", "/api/v1/jobs/2/analyze/-1"} {
		srv := New(nil, nil, nil, nil, &fakeAuth{authenticated: true}, true, &fakeReporter{})
		w := httptest.NewRecorder()
		srv.Handler().ServeHTTP(w, httptest.NewRequest("POST", path, nil))
		if w.Code != 403 {
			t.Fatalf("cross-user %s: %d", path, w.Code)
		}
	}
}

func TestAuthorizedControls(t *testing.T) {
	for _, tc := range []struct {
		name     string
		required bool
		admin    bool
		path     string
		method   string
	}{
		{"owner recommendation", true, false, "/api/v1/jobs/recommend/42", "POST"},
		{"owner analysis", true, false, "/api/v1/jobs/1/analyze/42", "POST"},
		{"admin stats", true, true, "/api/v1/admin/stats", "GET"},
		{"admin user support", true, true, "/api/v1/jobs/recommend/1", "POST"},
		{"demo recommendation", false, false, "/api/v1/jobs/recommend/1", "POST"},
		{"demo admin", false, false, "/api/v1/admin/stats", "GET"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var ids []int64
			if tc.admin {
				ids = []int64{42}
			}
			srv := New(&fakeUsers{}, &fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, &fakeAuth{authenticated: tc.required}, tc.required, nil, ids...)
			w := httptest.NewRecorder()
			srv.Handler().ServeHTTP(w, httptest.NewRequest(tc.method, tc.path, nil))
			if w.Code != 200 {
				t.Fatalf("%d: %s", w.Code, w.Body.String())
			}
		})
	}
}

func TestProtectedUserList(t *testing.T) {
	srv := New(nil, nil, nil, nil, &fakeAuth{authenticated: true, meUser: domain.UserResponse{ID: 42, Username: "owner"}}, true, nil)
	w := httptest.NewRecorder()
	srv.Handler().ServeHTTP(w, httptest.NewRequest("GET", "/api/v1/users", nil))
	if w.Code != 200 || w.Body.String() != "[{\"id\":42,\"username\":\"owner\",\"desired_job\":\"\",\"career_years\":0}]\n" {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
}

func TestDeletedAdministratorSessionDenied(t *testing.T) {
	srv := New(nil, nil, nil, nil, &fakeAuth{authenticated: true, meErr: domain.NotFound("User not found")}, true, &fakeReporter{}, 42)
	for _, path := range []string{"/api/v1/admin/stats", "/api/v1/users"} {
		w := httptest.NewRecorder()
		srv.Handler().ServeHTTP(w, httptest.NewRequest("GET", path, nil))
		if w.Code != 401 {
			t.Fatalf("%s: %d", path, w.Code)
		}
	}
}

// 실제 서명 세션의 두 전달 방식 모두 같은 권한 경계를 거쳐야 한다.
func TestSignedSessionAuthorization(t *testing.T) {
	store, err := sqlite.Open(filepath.Join(t.TempDir(), "auth.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	ctx := t.Context()
	if _, err := store.ApplyMigrations(ctx); err != nil {
		t.Fatal(err)
	}
	uid, err := store.Users.Insert(ctx, "member")
	if err != nil {
		t.Fatal(err)
	}
	if err := store.Users.UpsertSpec(ctx, uid, "backend", 0, nil); err != nil {
		t.Fatal(err)
	}
	sessions := auth.NewSessionManager("test-signing-key", time.Hour, false)
	service := auth.NewService(nil, sessions, store.Users, store.Identities)
	token, err := sessions.Issue(uid, "member")
	if err != nil {
		t.Fatal(err)
	}
	for _, bearer := range []bool{false, true} {
		for _, admin := range []bool{false, true} {
			var ids []int64
			if admin {
				ids = []int64{uid}
			}
			srv := New(store.Users, &fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, service, true, nil, ids...)
			w := httptest.NewRecorder()
			r := httptest.NewRequest("GET", "/api/v1/admin/stats", nil)
			if bearer {
				r.Header.Set("Authorization", "Bearer "+token)
			} else {
				r.AddCookie(&http.Cookie{Name: auth.SessionCookie, Value: token})
			}
			srv.Handler().ServeHTTP(w, r)
			want := 403
			if admin {
				want = 200
			}
			if w.Code != want {
				t.Fatalf("bearer=%v admin=%v got=%d", bearer, admin, w.Code)
			}
		}
	}
	if _, err := store.Users.Delete(ctx, uid); err != nil {
		t.Fatal(err)
	}
	srv := New(nil, nil, nil, nil, service, true, nil, uid)
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/api/v1/admin/stats", nil)
	r.Header.Set("Authorization", "Bearer "+token)
	srv.Handler().ServeHTTP(w, r)
	if w.Code != 401 {
		t.Fatalf("deleted account session accepted: %d", w.Code)
	}
}
