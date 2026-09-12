// Package vector는 임베딩 벡터의 직렬화와 유사도 계산을 담당한다.
// SQLite에는 float32 little-endian BLOB으로 저장한다.
package vector

import (
	"encoding/binary"
	"fmt"
	"math"
)

// Encode는 벡터를 float32 little-endian 바이트열로 직렬화한다.
func Encode(v []float32) []byte {
	buf := make([]byte, 4*len(v))
	for i, x := range v {
		binary.LittleEndian.PutUint32(buf[i*4:], math.Float32bits(x))
	}
	return buf
}

// Decode는 바이트열을 벡터로 복원한다.
func Decode(b []byte) ([]float32, error) {
	if len(b)%4 != 0 {
		return nil, fmt.Errorf("벡터 바이트열 길이가 4의 배수가 아님: %d", len(b))
	}
	v := make([]float32, len(b)/4)
	for i := range v {
		v[i] = math.Float32frombits(binary.LittleEndian.Uint32(b[i*4:]))
	}
	return v, nil
}

// Cosine은 두 벡터의 코사인 유사도를 돌려준다. 영벡터는 0으로 처리한다.
func Cosine(a, b []float32) float64 {
	if len(a) != len(b) || len(a) == 0 {
		return 0
	}
	var dot, normA, normB float64
	for i := range a {
		x, y := float64(a[i]), float64(b[i])
		dot += x * y
		normA += x * x
		normB += y * y
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}
