// Package llm은 상세 분석용 LLM 포트를 정의한다.
package llm

import (
	"context"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// AnalysisGenerator는 구조화된 상세 분석을 생성하는 포트다.
// 구현은 프롬프트를 받아 DetailedAnalysisResponse JSON을 돌려준다.
type AnalysisGenerator interface {
	GenerateAnalysis(ctx context.Context, prompt string) (domain.DetailedAnalysisResponse, error)
}
