// Package embedding은 임베딩 공급자의 포트(Embedder)와 레지스트리를 정의한다.
//
// 모든 소비자는 구현체가 아니라 Embedder 인터페이스에 의존하고, 조립 지점
// (composition root)에서 생성자 주입으로 구현체를 넣는다. 새 로컬/클라우드
// 공급자는 Factory를 레지스트리에 등록하는 것만으로 추가된다.
package embedding

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync/atomic"

	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
)

// Embedder는 텍스트 임베딩 공급자 포트다.
type Embedder interface {
	// EmbedDocuments는 저장할 문서들을 임베딩한다 (예: task_type=RETRIEVAL_DOCUMENT).
	EmbedDocuments(ctx context.Context, texts []string) ([][]float32, error)
	// EmbedQuery는 검색 쿼리 하나를 임베딩한다 (예: task_type=RETRIEVAL_QUERY).
	EmbedQuery(ctx context.Context, text string) ([]float32, error)
	// ModelKey는 DB model 컬럼에 저장하는 "provider:model" 식별자다.
	ModelKey() string
	// Dim은 출력 벡터 차원이다.
	Dim() int
}

// Factory는 설정으로 Embedder를 만드는 함수다.
type Factory func(config.Settings) (Embedder, error)

type provider struct {
	name         string
	factory      Factory
	defaultModel string
	defaultDim   int
}

// Registry는 등록된 임베딩 공급자 목록과 해석·생성을 담당한다.
type Registry struct {
	providers map[string]provider
}

func NewRegistry() *Registry {
	return &Registry{providers: map[string]provider{}}
}

// Register는 공급자를 등록한다.
func (r *Registry) Register(name string, defaultModel string, defaultDim int, factory Factory) {
	r.providers[name] = provider{name: name, factory: factory, defaultModel: defaultModel, defaultDim: defaultDim}
}

// Providers는 등록된 공급자 이름을 정렬해 돌려준다.
func (r *Registry) Providers() []string {
	out := make([]string, 0, len(r.providers))
	for name := range r.providers {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

// Resolve는 provider/model/dim을 Target으로 해석한다. Python resolve_target과 동일:
// model·dim 생략 시 공급자 기본값을 쓰고, 미등록 공급자는 오류이다.
func (r *Registry) Resolve(providerName, model string, dim *int) (domain.Target, error) {
	p, ok := r.providers[providerName]
	if !ok {
		return domain.Target{}, fmt.Errorf("알 수 없는 provider: %s (%s)",
			providerName, strings.Join(r.Providers(), " | "))
	}
	target := domain.Target{Provider: providerName, Model: model, Dim: 0}
	if target.Model == "" {
		target.Model = p.defaultModel
	}
	if dim != nil {
		target.Dim = *dim
	} else {
		target.Dim = p.defaultDim
	}
	return target, nil
}

// Build는 등록된 팩토리로 Embedder 인스턴스를 만든다.
func (r *Registry) Build(providerName string, s config.Settings) (Embedder, error) {
	p, ok := r.providers[providerName]
	if !ok {
		return nil, fmt.Errorf("알 수 없는 provider: %s (%s)",
			providerName, strings.Join(r.Providers(), " | "))
	}
	return p.factory(s)
}

// Models는 어드민 models 응답용 공급자 메타데이터를 정렬해 돌려준다.
func (r *Registry) Models() []domain.ModelInfo {
	names := r.Providers()
	out := make([]domain.ModelInfo, 0, len(names))
	for _, name := range names {
		p := r.providers[name]
		out = append(out, domain.ModelInfo{Provider: name, Model: p.defaultModel, Dim: p.defaultDim})
	}
	return out
}

// AtomicEmbedder는 실행 중 모델 전환을 위한 스레드세이프 Embedder 홀더다.
// 소비자는 Current()로 항상 최신 구현체를 얻는다.
type AtomicEmbedder struct {
	v atomic.Value // Embedder
}

func NewAtomic(e Embedder) *AtomicEmbedder {
	a := &AtomicEmbedder{}
	a.v.Store(&e)
	return a
}

func (a *AtomicEmbedder) Current() Embedder {
	if v, ok := a.v.Load().(*Embedder); ok && v != nil {
		return *v
	}
	return nil
}

// Swap은 전환된 Embedder로 교체한다.
func (a *AtomicEmbedder) Swap(e Embedder) { a.v.Store(&e) }

// Prefixes는 모델 계열별 (query, document) 접두어를 돌려준다.
// E5 계열만 접두어가 필요하다. 로컬 ONNX 구현 추가 시 그대로 쓴다.
func Prefixes(modelName string) (query, document string) {
	if strings.Contains(strings.ToLower(modelName), "e5") {
		return "query: ", "passage: "
	}
	return "", ""
}
