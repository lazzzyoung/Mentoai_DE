// Package analysis는 Gemini 상세 커리어 컨설팅과 캐시를 담당한다.
// 동일 모델과 동일 분석 입력에 대해 저장된 결과를 재사용한다.
package analysis

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/llm"
	"github.com/Chae-JS/mentoai/internal/recommend"
	"github.com/Chae-JS/mentoai/internal/storage"
)

// ANALYSIS_PROMPT는 원본과 동일한 지시문이다. {user_specs}/{company}/{title}/{content} 치환.
const analysisPrompt = `당신은 IT 대기업 및 유니콘 스타트업의 시니어 테크 리드(Tech Lead)이자 채용 최종 결정권자입니다.
지원자의 이력서와 공고를 비교 분석하여, 당장 실천 가능한 '합격 치트키' 수준의 전략을 수립하세요.

[지원자 프로필] {user_specs}
[목표 공고] {company} / {title}
[공고 내용]
{content}

**작성 지침 (Deep Dive):**

1. current_score (냉철한 평가): 50~85점 사이로 책정하고, 왜 감점되었는지를 액션 플랜에 녹여내세요.

2. required_tech_stack (핵심 파악): 공고에 나열된 기술 중, 지원자가 없으면 서류 광탈할 Critical Stack 3~5가지만 엄선하세요.

3. action_plan (초구체적 실행 가이드):
   - 추상적인 조언(예: "Kubernetes 공부하기")은 절대 금지입니다. How-to를 포함한 시나리오를 제시하세요.
   - 예시: "현재 보유한 FastAPI 프로젝트를 Docker 이미지로 빌드하고 AWS EKS에 배포하는 실습을 하세요. Terraform으로 인프라를 프로비저닝하여 IaC 경험을 포트폴리오에 추가해야 합니다."

4. interview_tip (면접관의 시선): 해당 회사의 도메인과 기술 스택을 결합한 예상 질문과 모범 답안 키워드를 알려주세요.
`

// SettingsProvider는 캐시 모델명 등 런타임 설정을 읽는다.
type SettingsProvider interface {
	GeminiModel() string
}

// Service는 상세 분석 서비스다.
type Service struct {
	users     storage.UserRepo
	jobs      storage.JobRepo
	cache     storage.CacheRepo
	generator llm.AnalysisGenerator
	settings  SettingsProvider
}

// New는 의존성을 주입받아 분석 서비스를 만든다.
func New(users storage.UserRepo, jobs storage.JobRepo, cache storage.CacheRepo, generator llm.AnalysisGenerator, settings SettingsProvider) *Service {
	return &Service{users: users, jobs: jobs, cache: cache, generator: generator, settings: settings}
}

// Analyze는 공고-사용자 조합의 상세 분석을 돌려준다(캐시 우선).
func (s *Service) Analyze(ctx context.Context, jobID, userID int64) (domain.DetailedAnalysisResponse, error) {
	var out domain.DetailedAnalysisResponse

	user, err := s.users.Info(ctx, userID)
	if err != nil {
		return out, err
	}
	if user == nil {
		return out, domain.NotFound("User not found")
	}
	job, err := s.jobs.GetFull(ctx, jobID)
	if err != nil {
		return out, err
	}
	if job == nil {
		return out, domain.NotFound("해당 공고를 찾을 수 없습니다.")
	}

	prompt := strings.NewReplacer(
		"{user_specs}", recommend.BuildProfileText(*user),
		"{company}", defaultStr(job.Company, "미상"),
		"{title}", defaultStr(job.Position, "미상"),
		"{content}", job.FullText,
	).Replace(analysisPrompt)

	// 프롬프트 전체를 검증하므로 프로필·공고·프롬프트 지침 변경과
	// 변경 전에 시작한 요청이 뒤늦게 저장하는 경우에도 오래된 결과를 쓰지 않는다.
	model := s.settings.GeminiModel()
	fingerprint := fmt.Sprintf("%x", sha256.Sum256([]byte(prompt)))
	if cached, ok, err := s.cache.Get(ctx, jobID, userID, model); err != nil {
		return out, err
	} else if ok {
		var entry cacheEntry
		if json.Unmarshal(cached, &entry) == nil && entry.Fingerprint == fingerprint {
			return entry.Response, nil
		}
	}

	result, err := s.generator.GenerateAnalysis(ctx, prompt)
	if err != nil {
		slog.Error("상세 분석 실패", "job_id", jobID, "user_id", userID, "error", err)
		return out, domain.AsHTTPError(err)
	}

	payload, err := json.Marshal(cacheEntry{Fingerprint: fingerprint, Response: result})
	if err != nil {
		return out, domain.AsHTTPError(err)
	}
	if err := s.cache.Upsert(ctx, jobID, userID, model, payload); err != nil {
		return out, domain.AsHTTPError(err)
	}
	return result, nil
}

// 기존 캐시(JSON 응답만 저장)는 fingerprint가 없어 한 번 재생성된다.
type cacheEntry struct {
	Fingerprint string                          `json:"fingerprint"`
	Response    domain.DetailedAnalysisResponse `json:"response"`
}

func defaultStr(s *string, def string) string {
	if s == nil || *s == "" {
		return def
	}
	return *s
}
