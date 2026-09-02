package api

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// authStatus는 GET /api/v1/auth/status 다. 프런트가 로그인 버튼을 그리는 데 쓴다.
func (s *Server) authStatus(w http.ResponseWriter, _ *http.Request) {
	status := s.auth.Status()
	status.AuthRequired = s.authRequired
	writeJSON(w, http.StatusOK, status)
}

// randomState는 OAuth state(CSRF 방어)용 무작위 문자열이다.
func randomState() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}

// authLogin은 GET /api/v1/auth/{provider}/login 다. 동의화면으로 302한다.
func (s *Server) authLogin(w http.ResponseWriter, r *http.Request) {
	provider := r.PathValue("provider")
	state, err := randomState()
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	loginURL, ok := s.auth.LoginURL(provider, state)
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"detail": "redirect 로그인을 지원하지 않거나 꺼진 공급자입니다: " + provider,
		})
		return
	}
	s.auth.SetStateCookie(w, state)
	http.Redirect(w, r, loginURL, http.StatusFound)
}

// authCallback은 GET /api/v1/auth/{provider}/callback 다.
// 구글 등 redirect 방식 공급자가 코드를 돌려주는 지점이다.
func (s *Server) authCallback(w http.ResponseWriter, r *http.Request) {
	provider := r.PathValue("provider")

	if expected := s.auth.StateCookie(r); expected == "" || expected != r.URL.Query().Get("state") {
		writeJSON(w, http.StatusBadRequest, map[string]string{"detail": "state 값이 일치하지 않습니다 (CSRF 의심)"})
		return
	}
	code := r.URL.Query().Get("code")
	if code == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"detail": "code 파라미터가 없습니다"})
		return
	}

	token, _, err := s.auth.Login(r.Context(), provider, code, "")
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	s.auth.SetSessionCookie(w, token)
	http.Redirect(w, r, "/", http.StatusFound)
}

type tossCallbackBody struct {
	AuthorizationCode      string `json:"authorizationCode"`
	AuthorizationCodeSnake string `json:"authorization_code"`
	Referrer               string `json:"referrer"`
}

// authTossCallback은 POST /api/v1/auth/toss/callback 다.
// 앱인토스 클라이언트 SDK(appLogin)가 받은 인가 코드를 받아 세션을 발급한다.
func (s *Server) authTossCallback(w http.ResponseWriter, r *http.Request) {
	var body tossCallbackBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"detail": "요청 본문을 해석할 수 없습니다"})
		return
	}
	code := body.AuthorizationCode
	if code == "" {
		code = body.AuthorizationCodeSnake
	}
	if code == "" {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"detail": "authorizationCode는 필수입니다"})
		return
	}

	token, user, err := s.auth.Login(r.Context(), "toss", code, body.Referrer)
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	s.auth.SetSessionCookie(w, token)
	writeJSON(w, http.StatusOK, map[string]any{"token": token, "user": user})
}

// authMe는 GET /api/v1/auth/me 다.
func (s *Server) authMe(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth.Authenticated(r)
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"detail": "로그인이 필요합니다"})
		return
	}
	user, err := s.auth.Me(r.Context(), userID)
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, user)
}

// authUpdateMe는 PUT /api/v1/auth/me 다.
func (s *Server) authUpdateMe(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth.Authenticated(r)
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"detail": "로그인이 필요합니다"})
		return
	}
	var p domain.ProfileUpdate
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"detail": "요청 본문을 해석할 수 없습니다"})
		return
	}
	user, err := s.auth.UpdateMe(r.Context(), userID, p)
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, user)
}

// authLogout은 POST /api/v1/auth/logout 다. 세션 쿠키를 만료시킨다.
func (s *Server) authLogout(w http.ResponseWriter, _ *http.Request) {
	s.auth.ClearSessionCookie(w)
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
