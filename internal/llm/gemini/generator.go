// Package gemini는 Gemini 구조화 출력(generateContent + responseSchema)으로
// 상세 분석을 생성하는 llm.AnalysisGenerator 참조 구현이다.
package gemini

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// DefaultModel은 기본 LLM 모델이다.
const DefaultModel = "gemini-3-flash-preview"

// Config는 생성자 주입용 설정이다.
type Config struct {
	APIKey     string
	Model      string
	BaseURL    string
	HTTPClient *http.Client
}

// Client는 llm.AnalysisGenerator 인터페이스를 만족한다.
type Client struct {
	apiKey  string
	model   string
	baseURL string
	http    *http.Client
}

// New는 Gemini LLM 클라이언트를 만든다.
func New(cfg Config) *Client {
	if cfg.Model == "" {
		cfg.Model = DefaultModel
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = "https://generativelanguage.googleapis.com/v1beta"
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 120 * time.Second}
	}
	return &Client{apiKey: cfg.APIKey, model: cfg.Model, baseURL: cfg.BaseURL, http: cfg.HTTPClient}
}

type generateRequest struct {
	Contents         []content        `json:"contents"`
	GenerationConfig generationConfig `json:"generationConfig"`
}

type content struct {
	Parts []part `json:"parts"`
}

type part struct {
	Text string `json:"text"`
}

type generationConfig struct {
	ResponseMimeType string         `json:"responseMimeType"`
	ResponseSchema   map[string]any `json:"responseSchema"`
}

type generateResponse struct {
	Candidates []struct {
		Content struct {
			Parts []struct {
				Text string `json:"text"`
			} `json:"parts"`
		} `json:"content"`
		FinishReason string `json:"finishReason"`
	} `json:"candidates"`
	Err *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

// responseSchema는 DetailedAnalysisResponse에 대응하는 Gemini 스키마다.
// Pydantic response_schema를 수동 변환한 것과 동일한 구조다.
func analysisSchema() map[string]any {
	str := map[string]any{"type": "string"}
	integer := map[string]any{"type": "integer"}
	strArray := map[string]any{"type": "array", "items": str}
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"job_title":           str,
			"company_name":        str,
			"current_score":       integer,
			"max_score":           integer,
			"analysis_summary":    str,
			"required_tech_stack": strArray,
			"action_plan": map[string]any{
				"type": "array",
				"items": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"category":          str,
						"item_name":         str,
						"description":       str,
						"expected_score_up": integer,
					},
					"required": []string{"category", "item_name", "description", "expected_score_up"},
				},
			},
			"interview_tip": str,
		},
		"required": []string{
			"job_title", "company_name", "current_score", "max_score",
			"analysis_summary", "required_tech_stack", "action_plan", "interview_tip",
		},
	}
}

// GenerateAnalysis는 프롬프트로 구조화 분석을 생성한다.
func (c *Client) GenerateAnalysis(ctx context.Context, prompt string) (domain.DetailedAnalysisResponse, error) {
	var out domain.DetailedAnalysisResponse

	body := generateRequest{
		Contents: []content{{Parts: []part{{Text: prompt}}}},
		GenerationConfig: generationConfig{
			ResponseMimeType: "application/json",
			ResponseSchema:   analysisSchema(),
		},
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return out, err
	}

	endpoint := c.baseURL + "/models/" + c.model + ":generateContent"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(raw))
	if err != nil {
		return out, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-goog-api-key", c.apiKey)

	resp, err := c.http.Do(req)
	if err != nil {
		return out, fmt.Errorf("gemini 생성 요청 실패: %w", err)
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return out, err
	}
	var parsed generateResponse
	if err := json.Unmarshal(data, &parsed); err != nil {
		return out, fmt.Errorf("gemini 생성 응답 파싱 실패 (status=%d): %w", resp.StatusCode, err)
	}
	if resp.StatusCode != http.StatusOK {
		msg := "알 수 없는 오류"
		if parsed.Err != nil {
			msg = parsed.Err.Message
		}
		return out, fmt.Errorf("gemini 생성 API 오류 (status=%d): %s", resp.StatusCode, msg)
	}
	if len(parsed.Candidates) == 0 || len(parsed.Candidates[0].Content.Parts) == 0 {
		return out, fmt.Errorf("gemini 응답 파싱 실패: 빈 후보 %q", string(data))
	}

	text := parsed.Candidates[0].Content.Parts[0].Text
	if err := json.Unmarshal([]byte(text), &out); err != nil {
		return out, fmt.Errorf("gemini 응답 파싱 실패: %q", truncate(text, 200))
	}
	return out, nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
