// Package scoring은 추천 점수/사유 휴리스틱 순수 함수들이다.
// LLM 없이 즉시 응답하기 위한 것으로, 원본 Python 로직과 결과가 동일하다.
package scoring

import (
	"fmt"
	"math"
	"strings"
)

// SimilarityToScore는 cosine similarity(0~1)를 40~99 점수로 변환한다.
func SimilarityToScore(similarity float64) int {
	score := int(math.Round(similarity * 100))
	if score < 40 {
		return 40
	}
	if score > 99 {
		return 99
	}
	return score
}

// SkillOverlap은 사용자 스킬 중 공고 기술스택(대소문자 무시)에 포함된 것을 돌려준다.
func SkillOverlap(userSkills, jobTags []string) []string {
	tags := make(map[string]struct{}, len(jobTags))
	for _, tag := range jobTags {
		if tag == "" {
			continue
		}
		tags[strings.ToLower(strings.TrimSpace(tag))] = struct{}{}
	}
	var out []string
	for _, skill := range userSkills {
		if _, ok := tags[strings.ToLower(strings.TrimSpace(skill))]; ok {
			out = append(out, skill)
		}
	}
	return out
}

// BuildReason은 추천 이유 한 줄을 만든다.
func BuildReason(userSkills []string, careerYears int, jobTags []string, annualFrom *int, isNewbie *bool) string {
	overlap := SkillOverlap(userSkills, jobTags)
	var parts []string
	if len(overlap) > 0 {
		shown := overlap
		if len(shown) > 5 {
			shown = shown[:5]
		}
		parts = append(parts, fmt.Sprintf("보유 스킬(%s)이 포지션 기술스택과 일치", strings.Join(shown, ", ")))
	} else {
		parts = append(parts, "희망 직무와 공고 문맥이 유사")
	}

	if annualFrom != nil && *annualFrom > 0 && careerYears < *annualFrom {
		parts = append(parts, fmt.Sprintf("경력 요건(%d년+)까지 %d년 부족", *annualFrom, *annualFrom-careerYears))
	} else if isNewbie != nil && *isNewbie {
		parts = append(parts, "신입 지원 가능")
	}
	return strings.Join(parts, ", ") + "."
}

// CareerLabel은 경력 요건 라벨을 만든다. Wanted의 '상한 없음'은 100으로 온다.
func CareerLabel(annualFrom, annualTo *int, isNewbie *bool) *string {
	if isNewbie != nil && *isNewbie {
		return ptr("신입 가능")
	}
	if annualFrom == nil {
		return nil
	}
	to := 0
	if annualTo != nil {
		to = *annualTo
	}
	if to >= 99 {
		return ptr(fmt.Sprintf("경력 %d년 이상", *annualFrom))
	}
	if to == 0 {
		to = *annualFrom
	}
	return ptr(fmt.Sprintf("경력 %d~%d년", *annualFrom, to))
}

func ptr[T any](v T) *T { return &v }
