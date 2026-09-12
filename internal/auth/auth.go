// Package auth는 외부 로그인(구글·앱인토스)과 세션을 담당한다.
// 모든 공급자는 Provider 포트로 추상화되고, 설정이 채워진 것만 활성화된다.
package auth

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/storage"
)

const SessionCookie = "mentoai_session"
const StateCookie = "mentoai_oauth_state"

// Identity는 로그인 성공 후 공급자가 알려준 사용자 식별 정보다.
type Identity struct {
	Provider       string
	ProviderUserID string
	Email          string
	Name           string
}

// Provider는 로그인 공급자 포트다.
type Provider interface {
	Name() string
	Enabled() bool
	// LoginURL은 redirect 방식(구글)의 동의화면 주소를 돌려준다.
	// redirect 방식이 아니면(앱인토스) false를 반환한다.
	LoginURL(state string) (string, bool)
	// Exchange는 인가 코드를 사용자 신원으로 바꾼다.
	Exchange(ctx context.Context, code, referrer string) (Identity, error)
}

// ---------- 세션 ----------

type sessionClaims struct {
	UserID   int64  `json:"uid"`
	Username string `json:"username"`
	Expires  int64  `json:"exp"`
}

// SessionManager는 무상태 HMAC-SHA256 세션 토큰을 다룬다.
// 토큰 형식: base64url(claims JSON) + "." + base64url(HMAC)
type SessionManager struct {
	secret []byte
	ttl    time.Duration
	secure bool
}

func NewSessionManager(secret string, ttl time.Duration, secureCookie bool) *SessionManager {
	return &SessionManager{secret: []byte(secret), ttl: ttl, secure: secureCookie}
}

// Issue는 사용자 세션 토큰을 발급한다.
func (m *SessionManager) Issue(userID int64, username string) (string, error) {
	claims := sessionClaims{UserID: userID, Username: username, Expires: time.Now().Add(m.ttl).Unix()}
	payload, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	body := base64.RawURLEncoding.EncodeToString(payload)
	return body + "." + m.sign(body), nil
}

// Verify는 토큰 서명과 만료를 검사한다.
func (m *SessionManager) Verify(token string) (*sessionClaims, error) {
	body, sig, ok := strings.Cut(token, ".")
	if !ok {
		return nil, errors.New("세션 토큰 형식이 잘못되었습니다")
	}
	if !hmac.Equal([]byte(sig), []byte(m.sign(body))) {
		return nil, errors.New("세션 토큰 서명이 일치하지 않습니다")
	}
	payload, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		return nil, errors.New("세션 토큰을 디코딩할 수 없습니다")
	}
	var claims sessionClaims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return nil, errors.New("세션 토큰을 해석할 수 없습니다")
	}
	if time.Now().Unix() >= claims.Expires {
		return nil, errors.New("세션이 만료되었습니다")
	}
	return &claims, nil
}

func (m *SessionManager) sign(body string) string {
	mac := hmac.New(sha256.New, m.secret)
	mac.Write([]byte(body))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

// SetSessionCookie는 로그인 세션 쿠키를 심는다.
func (m *SessionManager) SetSessionCookie(w http.ResponseWriter, token string) {
	http.SetCookie(w, &http.Cookie{
		Name:     SessionCookie,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   m.secure,
		MaxAge:   int(m.ttl.Seconds()),
	})
}

// ClearSessionCookie는 로그아웃 시 세션 쿠키를 만료시킨다.
func (m *SessionManager) ClearSessionCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name: SessionCookie, Value: "", Path: "/", HttpOnly: true,
		SameSite: http.SameSiteLaxMode, Secure: m.secure, MaxAge: -1,
	})
}

// SetStateCookie는 OAuth state(CSRF 방어)용 단기 쿠키를 심는다.
func (m *SessionManager) SetStateCookie(w http.ResponseWriter, state string) {
	http.SetCookie(w, &http.Cookie{
		Name: StateCookie, Value: state, Path: "/", HttpOnly: true,
		SameSite: http.SameSiteLaxMode, Secure: m.secure, MaxAge: 600,
	})
}

func (m *SessionManager) StateCookie(r *http.Request) string {
	if c, err := r.Cookie(StateCookie); err == nil {
		return c.Value
	}
	return ""
}

// FromRequest는 쿠키 또는 Authorization: Bearer에서 세션을 읽는다.
func (m *SessionManager) FromRequest(r *http.Request) (*sessionClaims, error) {
	token := ""
	if c, err := r.Cookie(SessionCookie); err == nil {
		token = c.Value
	} else if h := r.Header.Get("Authorization"); strings.HasPrefix(h, "Bearer ") {
		token = strings.TrimPrefix(h, "Bearer ")
	}
	if token == "" {
		return nil, errors.New("세션이 없습니다")
	}
	return m.Verify(token)
}

// ---------- 서비스 ----------

// Service는 로그인 처리(신원 → 사용자 매핑)와 세션 발급을 담당한다.
type Service struct {
	providers  []Provider
	sessions   *SessionManager
	users      storage.UserRepo
	identities storage.IdentityRepo
}

func NewService(providers []Provider, sessions *SessionManager, users storage.UserRepo, identities storage.IdentityRepo) *Service {
	return &Service{providers: providers, sessions: sessions, users: users, identities: identities}
}

// Status는 활성화된 공급자 목록을 돌려준다.
func (s *Service) Status() domain.AuthStatus {
	out := domain.AuthStatus{Providers: []domain.ProviderStatus{}}
	for _, p := range s.providers {
		status := domain.ProviderStatus{Provider: p.Name(), Enabled: p.Enabled()}
		if _, ok := p.LoginURL(""); ok {
			status.LoginPath = "/api/v1/auth/" + p.Name() + "/login"
		}
		out.Providers = append(out.Providers, status)
	}
	return out
}

// LoginURL은 redirect 방식 공급자의 동의화면 주소를 돌려준다.
func (s *Service) LoginURL(providerName, state string) (string, bool) {
	for _, p := range s.providers {
		if p.Name() == providerName {
			return p.LoginURL(state)
		}
	}
	return "", false
}

// Login은 인가 코드를 신원으로 바꾸고, 첫 로그인이면 사용자를 만들어 연결한 뒤
// 세션 토큰을 발급한다.
func (s *Service) Login(ctx context.Context, providerName, code, referrer string) (string, domain.UserResponse, error) {
	var out domain.UserResponse

	provider := s.provider(providerName)
	if provider == nil || !provider.Enabled() {
		return "", out, domain.BadRequest("사용할 수 없는 로그인 공급자: " + providerName)
	}
	identity, err := provider.Exchange(ctx, code, referrer)
	if err != nil {
		return "", out, err
	}

	// 기존 연결 찾기 → 없으면 자동 회원가입
	if userID, err := s.identities.FindUserID(ctx, identity.Provider, identity.ProviderUserID); err != nil {
		return "", out, err
	} else if userID != nil {
		user, err := s.userResponse(ctx, *userID)
		if err != nil {
			return "", out, err
		}
		token, err := s.sessions.Issue(*userID, user.Username)
		return token, user, err
	}

	userID, err := s.createUser(ctx, identity)
	if err != nil {
		return "", out, err
	}
	if err := s.identities.Link(ctx, identity.Provider, identity.ProviderUserID, userID); err != nil {
		return "", out, err
	}
	user, err := s.userResponse(ctx, userID)
	if err != nil {
		return "", out, err
	}
	token, err := s.sessions.Issue(userID, user.Username)
	return token, user, err
}

// Me는 로그인 사용자의 스펙을 돌려준다.
func (s *Service) Me(ctx context.Context, userID int64) (domain.UserResponse, error) {
	info, err := s.users.Info(ctx, userID)
	if err != nil {
		return domain.UserResponse{}, err
	}
	if info == nil {
		return domain.UserResponse{}, domain.NotFound("User not found")
	}
	return domain.UserResponse{
		ID: userID, Username: info.Username, DesiredJob: info.DesiredJob,
		CareerYears: info.CareerYears, Skills: defaultSkills(info.Skills),
	}, nil
}

// UpdateMe는 자기 스펙(직무/경력/스킬)을 수정한다. username은 불변이다.
func (s *Service) UpdateMe(ctx context.Context, userID int64, p domain.ProfileUpdate) (domain.UserResponse, error) {
	if err := p.Validate(); err != nil {
		return domain.UserResponse{}, domain.Unprocessable(err.Error())
	}
	row, err := s.users.GetByID(ctx, userID)
	if err != nil {
		return domain.UserResponse{}, err
	}
	if row == nil {
		return domain.UserResponse{}, domain.NotFound("User not found")
	}
	if err := s.users.UpsertSpec(ctx, userID, p.DesiredJob, p.CareerYears, p.Skills); err != nil {
		return domain.UserResponse{}, err
	}
	return domain.UserResponse{
		ID: userID, Username: row.Username, DesiredJob: p.DesiredJob,
		CareerYears: p.CareerYears, Skills: defaultSkills(p.Skills),
	}, nil
}

// createUser는 첫 로그인 사용자를 만든다. username 중복 시 접미사를 붙인다.
func (s *Service) createUser(ctx context.Context, identity Identity) (int64, error) {
	base := usernameFor(identity)
	name := base
	for i := 2; i <= 100; i++ {
		userID, err := s.users.Insert(ctx, name)
		if err != nil {
			return 0, err
		}
		if userID != 0 {
			if err := s.users.UpsertSpec(ctx, userID, "미지정", 0, []string{}); err != nil {
				return 0, err
			}
			return userID, nil
		}
		name = base + "-" + strconv.Itoa(i)
	}
	return 0, fmt.Errorf("사용자명을 생성할 수 없습니다: %s", base)
}

func (s *Service) userResponse(ctx context.Context, userID int64) (domain.UserResponse, error) {
	info, err := s.users.Info(ctx, userID)
	if err != nil {
		return domain.UserResponse{}, err
	}
	if info == nil {
		return domain.UserResponse{}, domain.NotFound("User not found")
	}
	return domain.UserResponse{
		ID: userID, Username: info.Username, DesiredJob: info.DesiredJob,
		CareerYears: info.CareerYears, Skills: defaultSkills(info.Skills),
	}, nil
}

func (s *Service) provider(name string) Provider {
	for _, p := range s.providers {
		if p.Name() == name {
			return p
		}
	}
	return nil
}

func usernameFor(identity Identity) string {
	if identity.Email != "" {
		if local, _, ok := strings.Cut(identity.Email, "@"); ok && local != "" {
			return local
		}
	}
	if identity.Name != "" {
		return identity.Name
	}
	return identity.Provider + "-user-" + identity.ProviderUserID
}

// ---------- API 위임 (api 패키지 포트 구현용) ----------

// SetSessionCookie는 로그인 성공 후 세션 쿠키를 심는다.
func (s *Service) SetSessionCookie(w http.ResponseWriter, token string) {
	s.sessions.SetSessionCookie(w, token)
}

// ClearSessionCookie는 로그아웃 쿠키를 심는다.
func (s *Service) ClearSessionCookie(w http.ResponseWriter) {
	s.sessions.ClearSessionCookie(w)
}

// SetStateCookie는 OAuth state 쿠키를 심는다.
func (s *Service) SetStateCookie(w http.ResponseWriter, state string) {
	s.sessions.SetStateCookie(w, state)
}

// StateCookie는 요청에서 OAuth state 쿠키 값을 읽는다.
func (s *Service) StateCookie(r *http.Request) string { return s.sessions.StateCookie(r) }

// Authenticated는 요청의 세션(쿠키 또는 Bearer)을 검증한다.
func (s *Service) Authenticated(r *http.Request) (userID int64, username string, ok bool) {
	claims, err := s.sessions.FromRequest(r)
	if err != nil {
		return 0, "", false
	}
	return claims.UserID, claims.Username, true
}

// Issue는 토큰만 필요한 호출(앱인토스 JSON 응답)을 위한 발급 위임이다.
func (s *Service) Issue(userID int64, username string) (string, error) {
	return s.sessions.Issue(userID, username)
}

func defaultSkills(skills []string) []string {
	if skills == nil {
		return []string{}
	}
	return skills
}
