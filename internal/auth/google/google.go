// Package google은 표준 OAuth2(OIDC) 구글 로그인 Provider다.
// net/http만으로 OAuth2 플로우를 구현한다(외부 SDK 없음).
package google

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/Chae-JS/mentoai/internal/auth"
)

const (
	defaultAuthBase = "https://accounts.google.com/o/oauth2/v2/auth"
	defaultTokenURL = "https://oauth2.googleapis.com/token"
	defaultUserinfo = "https://openidconnect.googleapis.com/v1/userinfo"
	scope           = "openid email profile"
	providerName    = "google"
)

// Config는 생성자 주입용 설정이다. 테스트에서 URL들을 갈아끼운다.
type Config struct {
	ClientID     string
	ClientSecret string
	RedirectURL  string
	AuthBaseURL  string // 기본: accounts.google.com 동의화면
	TokenURL     string // 기본: oauth2.googleapis.com/token
	UserinfoURL  string // 기본: openidconnect.googleapis.com/v1/userinfo
	HTTPClient   *http.Client
}

type Provider struct {
	cfg Config
}

// New는 구글 로그인 Provider를 만든다.
func New(cfg Config) *Provider {
	if cfg.AuthBaseURL == "" {
		cfg.AuthBaseURL = defaultAuthBase
	}
	if cfg.TokenURL == "" {
		cfg.TokenURL = defaultTokenURL
	}
	if cfg.UserinfoURL == "" {
		cfg.UserinfoURL = defaultUserinfo
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 15 * time.Second}
	}
	return &Provider{cfg: cfg}
}

// Enabled는 클라이언트 ID/시크릿이 모두 설정된 경우 참이다.
func (p *Provider) Enabled() bool {
	return p.cfg.ClientID != "" && p.cfg.ClientSecret != ""
}

// Name은 공급자 식별자다.
func (p *Provider) Name() string { return providerName }

// LoginURL은 구글 동의화면 주소를 만든다.
func (p *Provider) LoginURL(state string) (string, bool) {
	if !p.Enabled() {
		return "", false
	}
	q := url.Values{}
	q.Set("client_id", p.cfg.ClientID)
	q.Set("redirect_uri", p.cfg.RedirectURL)
	q.Set("response_type", "code")
	q.Set("scope", scope)
	q.Set("state", state)
	return p.cfg.AuthBaseURL + "?" + q.Encode(), true
}

type tokenResponse struct {
	AccessToken string `json:"access_token"`
	Error       string `json:"error"`
}

type userinfoResponse struct {
	Sub   string `json:"sub"`
	Email string `json:"email"`
	Name  string `json:"name"`
}

// Exchange는 인가 코드를 액세스 토큰으로 교환하고 사용자 정보를 조회한다.
func (p *Provider) Exchange(ctx context.Context, code, _ string) (auth.Identity, error) {
	var identity auth.Identity

	form := url.Values{}
	form.Set("code", code)
	form.Set("client_id", p.cfg.ClientID)
	form.Set("client_secret", p.cfg.ClientSecret)
	form.Set("redirect_uri", p.cfg.RedirectURL)
	form.Set("grant_type", "authorization_code")

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.cfg.TokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return identity, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := p.cfg.HTTPClient.Do(req)
	if err != nil {
		return identity, fmt.Errorf("구글 토큰 교환 실패: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return identity, err
	}
	var token tokenResponse
	if err := json.Unmarshal(raw, &token); err != nil {
		return identity, fmt.Errorf("구글 토큰 응답 파싱 실패 (status=%d): %w", resp.StatusCode, err)
	}
	if resp.StatusCode != http.StatusOK || token.AccessToken == "" {
		msg := token.Error
		if msg == "" {
			msg = "알 수 없는 오류"
		}
		return identity, fmt.Errorf("구글 토큰 교환 거부 (status=%d): %s", resp.StatusCode, msg)
	}

	infoReq, err := http.NewRequestWithContext(ctx, http.MethodGet, p.cfg.UserinfoURL, nil)
	if err != nil {
		return identity, err
	}
	infoReq.Header.Set("Authorization", "Bearer "+token.AccessToken)

	infoResp, err := p.cfg.HTTPClient.Do(infoReq)
	if err != nil {
		return identity, fmt.Errorf("구글 사용자 정보 조회 실패: %w", err)
	}
	defer infoResp.Body.Close()
	raw, err = io.ReadAll(infoResp.Body)
	if err != nil {
		return identity, err
	}
	if infoResp.StatusCode != http.StatusOK {
		return identity, fmt.Errorf("구글 사용자 정보 조회 거부 (status=%d): %s", infoResp.StatusCode, string(raw))
	}
	var info userinfoResponse
	if err := json.Unmarshal(raw, &info); err != nil {
		return identity, fmt.Errorf("구글 사용자 정보 파싱 실패: %w", err)
	}
	if info.Sub == "" {
		return identity, fmt.Errorf("구글 사용자 정보에 sub가 없습니다")
	}

	return auth.Identity{
		Provider:       providerName,
		ProviderUserID: info.Sub,
		Email:          info.Email,
		Name:           info.Name,
	}, nil
}
