// Package gemini는 Gemini Embedding API 기반 Embedder 참조 구현이다.
// 순수 net/http로만 동작한다 (공급자 SDK 의존 없음).
package gemini

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Chae-JS/mentoai/internal/config"
)

const (
	// DefaultModel과 DefaultDim은 어드민 전환 기본값이기도 하다.
	DefaultModel = "gemini-embedding-001"
	DefaultDim   = 1024
	// DefaultBaseURL은 Google Generative Language API 엔드포인트다.
	DefaultBaseURL = "https://generativelanguage.googleapis.com/v1beta"

	batchSize    = 100
	taskDocument = "RETRIEVAL_DOCUMENT"
	taskQuery    = "RETRIEVAL_QUERY"
)

// Config는 생성자 주입용 설정이다. 테스트에서 BaseURL/HTTPClient를 갈아끼운다.
type Config struct {
	APIKey     string
	Model      string
	Dim        int
	BaseURL    string
	HTTPClient *http.Client
}

// Client는 embedding.Embedder 인터페이스를 만족한다.
type Client struct {
	apiKey  string
	model   string
	dim     int
	baseURL string
	http    *http.Client
}

// New는 Gemini 임베딩 클라이언트를 만든다.
func New(cfg Config) *Client {
	if cfg.Model == "" {
		cfg.Model = DefaultModel
	}
	if cfg.Dim == 0 {
		cfg.Dim = DefaultDim
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = DefaultBaseURL
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 60 * time.Second}
	}
	return &Client{apiKey: cfg.APIKey, model: cfg.Model, dim: cfg.Dim, baseURL: cfg.BaseURL, http: cfg.HTTPClient}
}

// NewFromSettings는 config.Settings에서 클라이언트를 만든다(팩토리 어댑터용).
// API 키가 없어도 서버 기동은 가능하도록 생성 시점에는 검증하지 않고,
// 임베딩 호출 시점에 오류를 낸다.
func NewFromSettings(s config.Settings) (*Client, error) {
	return New(Config{
		APIKey: s.GoogleAPIKey,
		Model:  s.GeminiEmbeddingModel,
		Dim:    s.EmbeddingDim,
	}), nil
}

// ModelKey는 "gemini:<model>" 식별자를 돌려준다.
func (c *Client) ModelKey() string { return "gemini:" + c.model }

// Dim은 출력 차원을 돌려준다.
func (c *Client) Dim() int { return c.dim }

func (c *Client) EmbedDocuments(ctx context.Context, texts []string) ([][]float32, error) {
	return c.embedBatch(ctx, taskDocument, texts)
}

func (c *Client) EmbedQuery(ctx context.Context, text string) ([]float32, error) {
	vectors, err := c.embedBatch(ctx, taskQuery, []string{text})
	if err != nil {
		return nil, err
	}
	return vectors[0], nil
}

func (c *Client) embedBatch(ctx context.Context, taskType string, texts []string) ([][]float32, error) {
	vectors := make([][]float32, 0, len(texts))
	for start := 0; start < len(texts); start += batchSize {
		end := start + batchSize
		if end > len(texts) {
			end = len(texts)
		}
		vs, err := c.embedChunk(ctx, taskType, texts[start:end])
		if err != nil {
			return nil, err
		}
		vectors = append(vectors, vs...)
	}
	return vectors, nil
}

type embedRequest struct {
	Model                string       `json:"model"`
	Content              embedContent `json:"content"`
	TaskType             string       `json:"taskType,omitempty"`
	OutputDimensionality int          `json:"outputDimensionality,omitempty"`
}

type embedContent struct {
	Parts []embedPart `json:"parts"`
}

type embedPart struct {
	Text string `json:"text"`
}

type batchEmbedRequest struct {
	Requests []embedRequest `json:"requests"`
}

type batchEmbedResponse struct {
	Embeddings []struct {
		Values []float32 `json:"values"`
	} `json:"embeddings"`
	Err *apiError `json:"error"`
}

type apiError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Status  string `json:"status"`
}

func (c *Client) embedChunk(ctx context.Context, taskType string, texts []string) ([][]float32, error) {
	if c.apiKey == "" {
		return nil, fmt.Errorf("GOOGLE_API_KEY가 없습니다. .env에 먼저 설정하세요")
	}
	body := batchEmbedRequest{Requests: make([]embedRequest, len(texts))}
	for i, t := range texts {
		body.Requests[i] = embedRequest{
			Model:                "models/" + c.model,
			Content:              embedContent{Parts: []embedPart{{Text: t}}},
			TaskType:             taskType,
			OutputDimensionality: c.dim,
		}
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	endpoint := c.baseURL + "/models/" + c.model + ":batchEmbedContents"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-goog-api-key", c.apiKey)

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("gemini 임베딩 요청 실패: %w", err)
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var parsed batchEmbedResponse
	if err := json.Unmarshal(data, &parsed); err != nil {
		return nil, fmt.Errorf("gemini 임베딩 응답 파싱 실패 (status=%d): %w", resp.StatusCode, err)
	}
	if resp.StatusCode != http.StatusOK {
		msg := "알 수 없는 오류"
		if parsed.Err != nil {
			msg = parsed.Err.Message
		}
		return nil, fmt.Errorf("gemini 임베딩 API 오류 (status=%d): %s", resp.StatusCode, msg)
	}
	if len(parsed.Embeddings) != len(texts) {
		return nil, fmt.Errorf("gemini 임베딩 응답 수 불일치: 요청 %d / 응답 %d", len(texts), len(parsed.Embeddings))
	}

	out := make([][]float32, len(texts))
	for i, e := range parsed.Embeddings {
		out[i] = e.Values
	}
	return out, nil
}
