package embedding

import (
	"context"
	"testing"

	"github.com/Chae-JS/mentoai/internal/config"
)

func TestPrefixes(t *testing.T) {
	t.Parallel()
	if q, d := Prefixes("intfloat/multilingual-e5-large"); q != "query: " || d != "passage: " {
		t.Fatalf("e5 접두어: %q %q", q, d)
	}
	if q, d := Prefixes("BAAI/bge-m3"); q != "" || d != "" {
		t.Fatalf("bge는 접두어 없음: %q %q", q, d)
	}
}

type fakeEmbedder struct{ key string }

func (f fakeEmbedder) EmbedDocuments(context.Context, []string) ([][]float32, error) {
	return nil, nil
}
func (f fakeEmbedder) EmbedQuery(context.Context, string) ([]float32, error) {
	return nil, nil
}
func (f fakeEmbedder) ModelKey() string { return f.key }
func (f fakeEmbedder) Dim() int         { return 1024 }

func TestRegistryResolve(t *testing.T) {
	t.Parallel()
	reg := NewRegistry()
	reg.Register("gemini", "gemini-embedding-001", 1024,
		func(config.Settings) (Embedder, error) { return fakeEmbedder{"gemini:gemini-embedding-001"}, nil })

	// 기본값 해석
	target, err := reg.Resolve("gemini", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	if target.Model != "gemini-embedding-001" || target.Dim != 1024 {
		t.Fatalf("기본값 해석 실패: %+v", target)
	}
	if target.Key() != "gemini:gemini-embedding-001" {
		t.Fatalf("Key 불일치: %s", target.Key())
	}

	// 지정값 우선
	target, err = reg.Resolve("gemini", "other-model", nil)
	if err != nil || target.Model != "other-model" {
		t.Fatalf("모델 지정 실패: %+v %v", target, err)
	}

	// 미등록 provider
	if _, err := reg.Resolve("openai", "", nil); err == nil {
		t.Fatal("미등록 provider는 오류")
	} else if got := err.Error(); got[:len("알 수 없는 provider")] != "알 수 없는 provider" {
		t.Fatalf("오류 메시지: %q", got)
	}
}

func TestRegistryBuild(t *testing.T) {
	t.Parallel()
	reg := NewRegistry()
	reg.Register("gemini", "m", 1024,
		func(config.Settings) (Embedder, error) { return fakeEmbedder{"gemini:m"}, nil })
	e, err := reg.Build("gemini", config.Settings{})
	if err != nil {
		t.Fatal(err)
	}
	if e.ModelKey() != "gemini:m" {
		t.Fatalf("빌드 실패: %s", e.ModelKey())
	}
	if _, err := reg.Build("nope", config.Settings{}); err == nil {
		t.Fatal("미등록 빌드는 오류")
	}
}

func TestAtomicEmbedderSwap(t *testing.T) {
	t.Parallel()
	active := NewAtomic(fakeEmbedder{"a"})
	if active.Current().ModelKey() != "a" {
		t.Fatal("초기값")
	}
	active.Swap(fakeEmbedder{"b"})
	if active.Current().ModelKey() != "b" {
		t.Fatal("교체 실패")
	}
}
