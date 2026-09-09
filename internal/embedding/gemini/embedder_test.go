package gemini

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
)

// fakeServer는 batchEmbedContents 요청을 기록하고 고정 응답을 돌려준다.
type fakeServer struct {
	requests atomic.Int64
	bodies   []batchEmbedRequest
	taskType string
}

func (f *fakeServer) handler(t *testing.T) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("x-goog-api-key") != "test-key" {
			t.Errorf("API 키 헤더 누락")
		}
		raw, _ := io.ReadAll(r.Body)
		var body batchEmbedRequest
		if err := json.Unmarshal(raw, &body); err != nil {
			t.Fatalf("본문 파싱: %v", err)
		}
		f.bodies = append(f.bodies, body)
		if len(body.Requests) > 0 {
			f.taskType = body.Requests[0].TaskType
		}
		f.requests.Add(1)

		resp := batchEmbedResponse{}
		for range body.Requests {
			resp.Embeddings = append(resp.Embeddings, struct {
				Values []float32 `json:"values"`
			}{Values: []float32{0.1, 0.2, 0.3}})
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}
}

func newTestClient(t *testing.T, fake *fakeServer) *Client {
	srv := httptest.NewServer(fake.handler(t))
	t.Cleanup(srv.Close)
	return New(Config{APIKey: "test-key", Model: DefaultModel, Dim: 1024, BaseURL: srv.URL})
}

func TestEmbedQueryTaskTypeAndDim(t *testing.T) {
	fake := &fakeServer{}
	client := newTestClient(t, fake)

	vec, err := client.EmbedQuery(context.Background(), "검색어")
	if err != nil {
		t.Fatal(err)
	}
	if len(vec) != 3 {
		t.Fatalf("벡터 길이: %d", len(vec))
	}
	if fake.taskType != "RETRIEVAL_QUERY" {
		t.Fatalf("쿼리 task_type: %s", fake.taskType)
	}
	if dim := fake.bodies[0].Requests[0].OutputDimensionality; dim != 1024 {
		t.Fatalf("outputDimensionality: %d", dim)
	}
	if model := fake.bodies[0].Requests[0].Model; model != "models/gemini-embedding-001" {
		t.Fatalf("model 필드: %s", model)
	}
}

func TestEmbedDocumentsTaskType(t *testing.T) {
	fake := &fakeServer{}
	client := newTestClient(t, fake)

	if _, err := client.EmbedDocuments(context.Background(), []string{"문서1", "문서2"}); err != nil {
		t.Fatal(err)
	}
	if fake.taskType != "RETRIEVAL_DOCUMENT" {
		t.Fatalf("문서 task_type: %s", fake.taskType)
	}
}

func TestEmbedDocumentsBatchesAt100(t *testing.T) {
	fake := &fakeServer{}
	client := newTestClient(t, fake)

	texts := make([]string, 250)
	for i := range texts {
		texts[i] = "t"
	}
	vectors, err := client.EmbedDocuments(context.Background(), texts)
	if err != nil {
		t.Fatal(err)
	}
	if len(vectors) != 250 {
		t.Fatalf("전체 벡터 수: %d", len(vectors))
	}
	if fake.requests.Load() != 3 {
		t.Fatalf("배치 100 기준 3회 요청 기대: %d", fake.requests.Load())
	}
	if got := len(fake.bodies[2].Requests); got != 50 {
		t.Fatalf("마지막 배치 크기: %d", got)
	}
}

func TestModelKey(t *testing.T) {
	client := New(Config{APIKey: "k"})
	if got := client.ModelKey(); got != "gemini:gemini-embedding-001" {
		t.Fatalf("model_key: %s", got)
	}
	if client.Dim() != 1024 {
		t.Fatalf("dim: %d", client.Dim())
	}
}
