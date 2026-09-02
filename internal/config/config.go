// Package config는 .env와 환경변수에서 애플리케이션 설정을 읽어온다.
// 이미 설정된 환경변수가 .env 값보다 우선한다.
package config

import (
	"os"
	"strconv"
	"strings"
	"sync"

	"github.com/Chae-JS/mentoai/internal/envfile"
)

// Settings는 애플리케이션 전역 설정. 필드명은 기존 Python Settings와 1:1 대응한다.
type Settings struct {
	EnvFile    string
	SQLitePath string

	// serve 시작 시 마이그레이션 후 샘플 사용자를 자동 적재(멱등)한다.
	SeedOnStart bool

	GoogleAPIKey string
	GeminiModel  string

	EmbeddingProvider    string // 등록된 임베딩 provider 식별자 (예: gemini)
	EmbeddingModel       string // provider별 보조 모델 설정값 (확장용)
	EmbeddingCacheDir    string
	GeminiEmbeddingModel string
	EmbeddingDim         int

	WantedBaseURL      string
	WantedJobGroupID   string
	WantedJobIDs       string
	ScrapeMaxItems     int
	ScrapeDelaySeconds float64

	ScheduleEnabled  bool
	ScheduleCron     string
	ScheduleTimezone string

	RecommendTopK int

	// --- 인증 (값이 채워진 공급자만 활성화된다) ---
	AuthSecret         string // 세션 서명 키 (로그인 기능 마스터 스위치)
	AuthRequired       bool   // true면 admin·jobs API에 로그인 강제
	AuthCookieSecure   bool   // HTTPS 뒤에서 운영할 때 true
	GoogleClientID     string
	GoogleClientSecret string
	GoogleRedirectURL  string
	TossMTLSCertPath   string // 앱인토스 mTLS 클라이언트 인증서
	TossMTLSKeyPath    string
	TossAPIBaseURL     string

	// --- 텔레메트리 (에러 리포팅) ---
	SentryDSN         string // 비어 있으면 리포팅 완전 비활성(Noop)
	SentryEnvironment string // Sentry 환경 태그 (production/staging 등)
}

// Load는 .env를 환경변수에 반영한 뒤 Settings를 만든다.
func Load(envFile string) Settings {
	_ = envfile.Load(envFile)
	return Settings{
		EnvFile:     envFile,
		SQLitePath:  get("SQLITE_PATH", "data/mentoai.db"),
		SeedOnStart: getBool("SEED_ON_START", false),

		GoogleAPIKey: get("GOOGLE_API_KEY", ""),
		GeminiModel:  get("GEMINI_MODEL", "gemini-3-flash-preview"),

		EmbeddingProvider:    get("EMBEDDING_PROVIDER", "gemini"),
		EmbeddingModel:       get("EMBEDDING_MODEL", ""),
		EmbeddingCacheDir:    get("EMBEDDING_CACHE_DIR", ".models"),
		GeminiEmbeddingModel: get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
		EmbeddingDim:         getInt("EMBEDDING_DIM", 1024),

		WantedBaseURL:      get("WANTED_BASE_URL", "https://www.wanted.co.kr"),
		WantedJobGroupID:   get("WANTED_JOB_GROUP_ID", "518"),
		WantedJobIDs:       get("WANTED_JOB_IDS", "655"),
		ScrapeMaxItems:     getInt("SCRAPE_MAX_ITEMS", 120),
		ScrapeDelaySeconds: getFloat("SCRAPE_DELAY_SECONDS", 0.4),

		ScheduleEnabled:  getBool("SCHEDULE_ENABLED", false),
		ScheduleCron:     get("SCHEDULE_CRON", "0 9,16 * * *"),
		ScheduleTimezone: get("SCHEDULE_TIMEZONE", "Asia/Seoul"),

		RecommendTopK: getInt("RECOMMEND_TOP_K", 5),

		AuthSecret:         get("AUTH_SECRET", ""),
		AuthRequired:       getBool("AUTH_REQUIRED", false),
		AuthCookieSecure:   getBool("AUTH_COOKIE_SECURE", false),
		GoogleClientID:     get("GOOGLE_CLIENT_ID", ""),
		GoogleClientSecret: get("GOOGLE_CLIENT_SECRET", ""),
		GoogleRedirectURL:  get("GOOGLE_REDIRECT_URL", "http://localhost:8000/api/v1/auth/google/callback"),
		TossMTLSCertPath:   get("TOSS_MTLS_CERT_PATH", ""),
		TossMTLSKeyPath:    get("TOSS_MTLS_KEY_PATH", ""),
		TossAPIBaseURL:     get("TOSS_API_BASE_URL", ""),

		SentryDSN:         get("SENTRY_DSN", ""),
		SentryEnvironment: get("SENTRY_ENVIRONMENT", "production"),
	}
}

// Holder는 실행 중 설정 교체(임베딩 모델 전환)를 위한 스레드세이프 저장소다.
// 모든 소비자는 생성 시 Holder를 주입받고 Get()으로 최신 설정을 읽는다.
type Holder struct {
	mu sync.RWMutex
	s  Settings
}

func NewHolder(s Settings) *Holder { return &Holder{s: s} }

func (h *Holder) Get() Settings {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return h.s
}

func (h *Holder) Set(s Settings) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.s = s
}

func get(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && strings.TrimSpace(v) != "" {
		return v
	}
	return def
}

func getInt(key string, def int) int {
	if v, ok := os.LookupEnv(key); ok {
		if n, err := strconv.Atoi(strings.TrimSpace(v)); err == nil {
			return n
		}
	}
	return def
}

func getFloat(key string, def float64) float64 {
	if v, ok := os.LookupEnv(key); ok {
		if f, err := strconv.ParseFloat(strings.TrimSpace(v), 64); err == nil {
			return f
		}
	}
	return def
}

func getBool(key string, def bool) bool {
	if v, ok := os.LookupEnv(key); ok {
		switch strings.ToLower(strings.TrimSpace(v)) {
		case "true", "1", "yes", "on":
			return true
		case "false", "0", "no", "off":
			return false
		}
	}
	return def
}
