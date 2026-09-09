// Package recommend은 벡터 유사도 + 휴리스틱으로 채용공고를 추천한다.
// LLM 호출이 없어 즉시 응답한다.
package recommend

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/embedding"
	"github.com/Chae-JS/mentoai/internal/scoring"
	"github.com/Chae-JS/mentoai/internal/storage"
)

// EmbedderProvider는 현재 활성 임베딩 구현을 제공한다.
// embedding.Embedder는 검색에 필요한 메서드만 노출하는 좁은 포트로 쓰인다.
type EmbedderProvider interface {
	Current() embedding.Embedder
}

// SettingsProvider는 추천 top_k 같은 런타임 설정을 읽는다.
type SettingsProvider interface {
	RecommendTopK() int
}

// Service는 추천 서비스다.
type Service struct {
	users    storage.UserRepo
	embeds   storage.EmbeddingRepo
	jobs     storage.JobRepo
	embedder EmbedderProvider
	settings SettingsProvider
}

// New는 의존성을 주입받아 추천 서비스를 만든다.
func New(users storage.UserRepo, embeds storage.EmbeddingRepo, jobs storage.JobRepo, embedder EmbedderProvider, settings SettingsProvider) *Service {
	return &Service{users: users, embeds: embeds, jobs: jobs, embedder: embedder, settings: settings}
}

// BuildProfileText는 사용자 스펙을 임베딩 쿼리 텍스트로 만든다.
func BuildProfileText(user domain.UserInfo) string {
	return fmt.Sprintf("희망직무: %s, 보유기술: %s, 경력: %d년",
		user.DesiredJob, strings.Join(user.Skills, ", "), user.CareerYears)
}

// Recommend는 사용자 프로필과 유사한 공고 상위 k건을 돌려준다.
func (s *Service) Recommend(ctx context.Context, userID int64) (domain.RecommendationListResponse, error) {
	var out domain.RecommendationListResponse

	user, err := s.users.Info(ctx, userID)
	if err != nil {
		return out, err
	}
	if user == nil {
		return out, domain.NotFound("User not found")
	}

	queryVector, err := s.embedder.Current().EmbedQuery(ctx, BuildProfileText(*user))
	if err != nil {
		slog.Error("추천 조회 실패", "user_id", userID, "error", err)
		return out, domain.AsHTTPError(err)
	}

	hits, err := s.embeds.SearchTopK(ctx, queryVector, s.settings.RecommendTopK())
	if err != nil {
		slog.Error("추천 조회 실패", "user_id", userID, "error", err)
		return out, domain.AsHTTPError(err)
	}

	ids := make([]int64, len(hits))
	for i, h := range hits {
		ids[i] = h.JobID
	}
	metas, err := s.jobs.GetMetaByIDs(ctx, ids)
	if err != nil {
		slog.Error("추천 조회 실패", "user_id", userID, "error", err)
		return out, domain.AsHTTPError(err)
	}

	recommendations := []domain.JobSummary{}
	for _, hit := range hits {
		meta, ok := metas[hit.JobID]
		if !ok {
			continue // 임베딩은 있지만 공고가 삭제된 경우
		}
		recommendations = append(recommendations, toJobSummary(hit, meta, user.Skills, user.CareerYears))
	}
	return domain.RecommendationListResponse{UserName: user.Username, Recommendations: recommendations}, nil
}

func toJobSummary(hit domain.SearchHit, meta domain.JobMeta, userSkills []string, careerYears int) domain.JobSummary {
	skills := meta.SkillTags
	if len(skills) > 4 {
		skills = skills[:4]
	}
	return domain.JobSummary{
		JobID:         meta.ID,
		Company:       defaultStr(meta.Company, "미상"),
		Title:         defaultStr(meta.Position, "미상"),
		Source:        meta.Source,
		Career:        scoring.CareerLabel(meta.AnnualFrom, meta.AnnualTo, meta.IsNewbie),
		Location:      meta.Location,
		Skills:        skills,
		MatchedSkills: scoring.SkillOverlap(userSkills, meta.SkillTags),
		MatchScore:    scoring.SimilarityToScore(hit.Similarity),
		MaxScore:      100,
		Reason:        scoring.BuildReason(userSkills, careerYears, meta.SkillTags, meta.AnnualFrom, meta.IsNewbie),
	}
}

func defaultStr(s *string, def string) string {
	if s == nil || *s == "" {
		return def
	}
	return *s
}
