// Package toss는 앱인토스(App in Toss) 토스 로그인 Provider다.
//
// 클라이언트 SDK(@apps-in-toss/web-framework의 appLogin())가 받은 인가 코드를
// 서버에서 액세스 토큰으로 교환하고 userKey를 조회한다.
// generate-token 호출은 mTLS 클라이언트 인증서가 필요하다(토스 콘솔 발급).
// 참고: https://developers-apps-in-toss.toss.im/documentation/common/authentication/toss-login
package toss

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Chae-JS/mentoai/internal/auth"
)

const (
	DefaultBaseURL = "https://apps-in-toss-api.toss.im"
	providerName   = "toss"

	tokenPath   = "/api-partner/v1/apps-in-toss/user/oauth2/generate-token"
	loginMePath = "/api-partner/v1/apps-in-toss/user/oauth2/login-me"
)

// Config는 생성자 주입용 설정이다. 테스트에서 BaseURL과 HTTPClient를 갈아끼운다.
type Config struct {
	BaseURL    string
	CertPath   string       // mTLS 클라이언트 인증서 (토스 콘솔 발급)
	KeyPath    string       // mTLS 클라이언트 개인키
	HTTPClient *http.Client // 주입되면 Cert/Key 대신 사용한다 (테스트용)
}

type Provider struct {
	cfg  Config
	http *http.Client
}

// New는 토스 로그인 Provider를 만든다. 인증서 경로가 주어지면 mTLS 클라이언트를
// 구성한다. 인증서 파일을 읽지 못하면 오류를 반환한다(기동 실패로 조기 발견).
func New(cfg Config) (*Provider, error) {
	if cfg.BaseURL == "" {
		cfg.BaseURL = DefaultBaseURL
	}
	if cfg.HTTPClient == nil {
		if cfg.CertPath == "" || cfg.KeyPath == "" {
			return &Provider{cfg: cfg, http: &http.Client{Timeout: 15 * time.Second}}, nil
		}
		cert, err := tls.LoadX509KeyPair(cfg.CertPath, cfg.KeyPath)
		if err != nil {
			return nil, fmt.Errorf("토스 mTLS 인증서 로드 실패: %w", err)
		}
		cfg.HTTPClient = &http.Client{
			Timeout: 15 * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{Certificates: []tls.Certificate{cert}},
			},
		}
	}
	return &Provider{cfg: cfg, http: cfg.HTTPClient}, nil
}

// Enabled는 인증서(또는 주입된 클라이언트)가 준비된 경우 참이다.
func (p *Provider) Enabled() bool {
	return p.http != nil && (p.cfg.HTTPClient != nil || (p.cfg.CertPath != "" && p.cfg.KeyPath != ""))
}

// Name은 공급자 식별자다.
func (p *Provider) Name() string { return providerName }

// LoginURL은 redirect 방식이 아니다 — 인가 코드는 클라이언트 SDK(appLogin)가 받는다.
func (p *Provider) LoginURL(string) (string, bool) { return "", false }

type generateTokenRequest struct {
	AuthorizationCode string `json:"authorizationCode"`
	Referrer          string `json:"referrer"`
}

type generateTokenResponse struct {
	TokenType   string `json:"tokenType"`
	AccessToken string `json:"accessToken"`
	Error       string `json:"error"`
}

type loginMeResponse struct {
	UserKey int64 `json:"userKey"`
}

// Exchange는 인가 코드로 토큰을 발급받고 userKey를 조회한다.
func (p *Provider) Exchange(ctx context.Context, code, referrer string) (auth.Identity, error) {
	var identity auth.Identity
	if referrer == "" {
		referrer = "DEFAULT"
	}

	body, err := json.Marshal(generateTokenRequest{AuthorizationCode: code, Referrer: referrer})
	if err != nil {
		return identity, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.cfg.BaseURL+tokenPath, bytes.NewReader(body))
	if err != nil {
		return identity, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.http.Do(req)
	if err != nil {
		return identity, fmt.Errorf("토스 토큰 발급 요청 실패: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return identity, err
	}
	var token generateTokenResponse
	if err := json.Unmarshal(raw, &token); err != nil {
		return identity, fmt.Errorf("토스 토큰 응답 파싱 실패 (status=%d): %w", resp.StatusCode, err)
	}
	if resp.StatusCode != http.StatusOK || token.AccessToken == "" {
		msg := token.Error
		if msg == "" {
			msg = "알 수 없는 오류"
		}
		return identity, fmt.Errorf("토스 토큰 발급 거부 (status=%d): %s", resp.StatusCode, msg)
	}

	meReq, err := http.NewRequestWithContext(ctx, http.MethodGet, p.cfg.BaseURL+loginMePath, nil)
	if err != nil {
		return identity, err
	}
	meReq.Header.Set("Authorization", "Bearer "+token.AccessToken)

	meResp, err := p.http.Do(meReq)
	if err != nil {
		return identity, fmt.Errorf("토스 사용자 정보 조회 실패: %w", err)
	}
	defer meResp.Body.Close()
	raw, err = io.ReadAll(meResp.Body)
	if err != nil {
		return identity, err
	}
	if meResp.StatusCode != http.StatusOK {
		return identity, fmt.Errorf("토스 사용자 정보 조회 거부 (status=%d): %s", meResp.StatusCode, string(raw))
	}
	var me loginMeResponse
	if err := json.Unmarshal(raw, &me); err != nil {
		return identity, fmt.Errorf("토스 사용자 정보 파싱 실패: %w", err)
	}
	if me.UserKey == 0 {
		return identity, fmt.Errorf("토스 사용자 정보에 userKey가 없습니다")
	}

	return auth.Identity{
		Provider:       providerName,
		ProviderUserID: fmt.Sprint(me.UserKey),
		Name:           "토스사용자",
	}, nil
}
