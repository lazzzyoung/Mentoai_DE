// Package domain은 저장소·서비스·API가 공유하는 타입과 오류를 정의한다.
package domain

import "fmt"

// ---------- API 응답 DTO ----------

type UserSummary struct {
	ID          int64  `json:"id"`
	Username    string `json:"username"`
	DesiredJob  string `json:"desired_job"`
	CareerYears int    `json:"career_years"`
}

type JobSummary struct {
	JobID         int64    `json:"job_id"`
	Company       string   `json:"company"`
	Title         string   `json:"title"`
	Source        *string  `json:"source"`
	Career        *string  `json:"career"`
	Location      *string  `json:"location"`
	Skills        []string `json:"skills"`
	MatchedSkills []string `json:"matched_skills"`
	MatchScore    int      `json:"match_score"`
	MaxScore      int      `json:"max_score"`
	Reason        string   `json:"reason"`
}

type RecommendationListResponse struct {
	UserName        string       `json:"user_name"`
	Recommendations []JobSummary `json:"recommendations"`
}

type ActionItem struct {
	Category        string `json:"category"`
	ItemName        string `json:"item_name"`
	Description     string `json:"description"`
	ExpectedScoreUp int    `json:"expected_score_up"`
}

type DetailedAnalysisResponse struct {
	JobTitle          string       `json:"job_title"`
	CompanyName       string       `json:"company_name"`
	CurrentScore      int          `json:"current_score"`
	MaxScore          int          `json:"max_score"`
	AnalysisSummary   string       `json:"analysis_summary"`
	RequiredTechStack []string     `json:"required_tech_stack"`
	ActionPlan        []ActionItem `json:"action_plan"`
	InterviewTip      string       `json:"interview_tip"`
}

// UserPayload는 어드민 사용자 등록/수정 요청 본문이다.
type UserPayload struct {
	Username    string   `json:"username"`
	DesiredJob  string   `json:"desired_job"`
	CareerYears int      `json:"career_years"`
	Skills      []string `json:"skills"`
}

// Validate는 pydantic 제약(username 1~30, desired_job 1~60, career_years 0~40,
// skills 최대 20개)을 검사한다.
func (p UserPayload) Validate() error {
	if n := len(p.Username); n < 1 || n > 30 {
		return fmt.Errorf("username은 1~30자여야 합니다")
	}
	if n := len(p.DesiredJob); n < 1 || n > 60 {
		return fmt.Errorf("desired_job은 1~60자여야 합니다")
	}
	if p.CareerYears < 0 || p.CareerYears > 40 {
		return fmt.Errorf("career_years는 0~40이어야 합니다")
	}
	if len(p.Skills) > 20 {
		return fmt.Errorf("skills는 최대 20개까지 가능합니다")
	}
	return nil
}

// UserResponse는 어드민 사용자 등록/수정 응답이다.
type UserResponse struct {
	ID          int64    `json:"id"`
	Username    string   `json:"username"`
	DesiredJob  string   `json:"desired_job"`
	CareerYears int      `json:"career_years"`
	Skills      []string `json:"skills"`
}

// ---------- 인증 ----------

type ProviderStatus struct {
	Provider  string `json:"provider"`
	Enabled   bool   `json:"enabled"`
	LoginPath string `json:"login_path,omitempty"` // redirect 방식(구글)만 제공
}

type AuthStatus struct {
	AuthRequired bool             `json:"auth_required"`
	Providers    []ProviderStatus `json:"providers"`
}

// ProfileUpdate는 로그인 사용자가 자기 스펙을 수정할 때의 본문이다.
type ProfileUpdate struct {
	DesiredJob  string   `json:"desired_job"`
	CareerYears int      `json:"career_years"`
	Skills      []string `json:"skills"`
}

// Validate는 UserPayload와 같은 제약을 username 없이 검사한다.
func (p ProfileUpdate) Validate() error {
	if n := len(p.DesiredJob); n < 1 || n > 60 {
		return fmt.Errorf("desired_job은 1~60자여야 합니다")
	}
	if p.CareerYears < 0 || p.CareerYears > 40 {
		return fmt.Errorf("career_years는 0~40이어야 합니다")
	}
	if len(p.Skills) > 20 {
		return fmt.Errorf("skills는 최대 20개까지 가능합니다")
	}
	return nil
}

// ---------- 어드민 조회 DTO ----------

type Sizes struct {
	BronzeSize     string `json:"bronze_size"`
	JobsSize       string `json:"jobs_size"`
	EmbeddingsSize string `json:"embeddings_size"`
}

type ScheduleInfo struct {
	Enabled  bool    `json:"enabled"`
	Cron     string  `json:"cron"`
	Timezone string  `json:"timezone"`
	NextRun  *string `json:"next_run"`
}

type RunRow struct {
	ID             int64   `json:"id"`
	Status         string  `json:"status"`
	StartedAt      string  `json:"started_at"`
	FinishedAt     *string `json:"finished_at"`
	Scraped        *int64  `json:"scraped"`
	SilverUpserted *int64  `json:"silver_upserted"`
	Embedded       *int64  `json:"embedded"`
	Error          *string `json:"error"`
}

type Status struct {
	Bronze         int64        `json:"bronze"`
	Jobs           int64        `json:"jobs"`
	Embeddings     int64        `json:"embeddings"`
	Users          int64        `json:"users"`
	CachedAnalyses int64        `json:"cached_analyses"`
	Sizes          Sizes        `json:"sizes"`
	EmbeddingModel string       `json:"embedding_model"`
	EmbeddingDim   int          `json:"embedding_dim"`
	GeminiModel    string       `json:"gemini_model"`
	Schedule       ScheduleInfo `json:"schedule"`
	Running        []string     `json:"running"`
	LastRun        *RunRow      `json:"last_run"`
}

type JobAdminRow struct {
	ID        int64    `json:"id"`
	Source    string   `json:"source"`
	SourceID  string   `json:"source_id"`
	Company   *string  `json:"company"`
	Position  *string  `json:"position"`
	SkillTags []string `json:"skill_tags"`
	UpdatedAt string   `json:"updated_at"`
}

type CacheRow struct {
	JobID     int64   `json:"job_id"`
	UserID    int64   `json:"user_id"`
	Model     string  `json:"model"`
	CreatedAt string  `json:"created_at"`
	Username  string  `json:"username"`
	Company   *string `json:"company"`
	Position  *string `json:"position"`
}

// ModelInfo는 등록된 임베딩 provider 한 건의 메타데이터다.
type ModelInfo struct {
	Provider string `json:"provider"`
	Model    string `json:"model"`
	Dim      int    `json:"dim"`
}

type EmbeddingModels struct {
	Current       string      `json:"current"`
	Provider      string      `json:"provider"`
	Dim           int         `json:"dim"`
	Available     []ModelInfo `json:"available"`
	GeminiDefault string      `json:"gemini_default"`
}

// ---------- 저장소 행 / 파이프라인 ----------

type UserRow struct {
	ID       int64
	Username string
}

type UserInfo struct {
	Username    string
	DesiredJob  string
	CareerYears int
	Skills      []string
}

type JobKey struct {
	Source   string
	SourceID string
	Company  *string
	Position *string
}

// JobMeta는 추천 하이드레이션에 필요한 공고 메타데이터다.
type JobMeta struct {
	ID         int64
	Source     *string
	Company    *string
	Position   *string
	SkillTags  []string
	AnnualFrom *int
	AnnualTo   *int
	IsNewbie   *bool
	Location   *string
}

type JobFull struct {
	ID       int64
	Company  *string
	Position *string
	FullText string
}

// SilverRow는 silver.jobs에 적재되는 정제 행이다.
type SilverRow struct {
	Source         string
	SourceID       string
	Company        *string
	Position       *string
	Location       *string
	Intro          *string
	MainTasks      *string
	Requirements   *string
	PreferredPoint *string
	Benefits       *string
	EmploymentType *string
	IsNewbie       *bool
	AnnualFrom     *int
	AnnualTo       *int
	DueTime        string
	SkillTags      []string
	Pay            *string
	Link           *string
	Deadline       *string
	FullText       string
	CollectedAt    string // RFC3339Nano UTC
}

// RawRecord는 bronze에 담길 원본 수집 레코드다. Payload는 원본 JSON 그대로다.
type RawRecord struct {
	Source      string
	SourceID    string
	CollectedAt string // RFC3339Nano UTC
	Payload     []byte
}

type PendingJob struct {
	ID       int64
	FullText string
}

type EmbeddingRow struct {
	JobID  int64
	Vector []float32
	Model  string
}

type SearchHit struct {
	JobID      int64
	Similarity float64
}

type PipelineResult struct {
	Scraped        int `json:"scraped"`
	SilverUpserted int `json:"silver_upserted"`
	Embedded       int `json:"embedded"`
}

// ---------- 임베딩 전환 ----------

type Target struct {
	Provider string
	Model    string
	Dim      int
}

func (t Target) Key() string { return t.Provider + ":" + t.Model }

type SwitchResult struct {
	Provider   string `json:"provider"`
	Model      string `json:"model"`
	Dim        int    `json:"dim"`
	ReEmbedded int    `json:"re_embedded"`
	EnvBackup  string `json:"env_backup"`
}

// ---------- 오류 ----------

// HTTPError는 서비스 계층이 HTTP 상태와 함께 전달하고 싶은 오류다.
// 핸들러는 이 오류를 그대로 응답으로 변환하고, 나머지는 500으로 감싼다.
type HTTPError struct {
	Code   int
	Detail string
}

func (e *HTTPError) Error() string { return e.Detail }

func NotFound(detail string) *HTTPError   { return &HTTPError{Code: 404, Detail: detail} }
func Conflict(detail string) *HTTPError   { return &HTTPError{Code: 409, Detail: detail} }
func BadRequest(detail string) *HTTPError { return &HTTPError{Code: 400, Detail: detail} }

// Unprocessable은 pydantic 검증 실패에 해당하는 422 오류다.
func Unprocessable(detail string) *HTTPError { return &HTTPError{Code: 422, Detail: detail} }

// AsHTTPError는 err가 *HTTPError면 반환하고 아니면 500으로 감싼다.
func AsHTTPError(err error) *HTTPError {
	if he, ok := err.(*HTTPError); ok {
		return he
	}
	return &HTTPError{Code: 500, Detail: err.Error()}
}
