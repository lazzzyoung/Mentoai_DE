package vector

import (
	"bytes"
	"math"
	"testing"
)

func TestEncodeDecodeRoundtrip(t *testing.T) {
	t.Parallel()
	original := []float32{0.25, -1.5, 3.25, 0}
	decoded, err := Decode(Encode(original))
	if err != nil {
		t.Fatal(err)
	}
	if len(decoded) != len(original) {
		t.Fatalf("길이 불일치: %d", len(decoded))
	}
	for i := range original {
		if decoded[i] != original[i] {
			t.Fatalf("%d번 값 불일치: %v != %v", i, decoded[i], original[i])
		}
	}
}

func TestDecodeRejectsBadLength(t *testing.T) {
	t.Parallel()
	if _, err := Decode([]byte{1, 2, 3}); err == nil {
		t.Fatal("4의 배수가 아닌 길이는 오류여야 한다")
	}
}

func TestCosine(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		a, b []float32
		want float64
	}{
		{"동일 벡터", []float32{1, 0, 1}, []float32{1, 0, 1}, 1},
		{"직교", []float32{1, 0}, []float32{0, 1}, 0},
		{"반대", []float32{1, 0}, []float32{-1, 0}, -1},
		{"영벡터", []float32{0, 0}, []float32{1, 0}, 0},
	}
	for _, c := range cases {
		if got := Cosine(c.a, c.b); math.Abs(got-c.want) > 1e-6 {
			t.Errorf("%s: got=%v want=%v", c.name, got, c.want)
		}
	}
}

func TestEncodeIsLittleEndianBlob(t *testing.T) {
	t.Parallel()
	b := Encode([]float32{1})
	if !bytes.Equal(b, []byte{0, 0, 0x80, 0x3f}) {
		t.Fatalf("little-endian float32 기대: %v", b)
	}
}

// FuzzDecode는 임의 바이트열이 패닉 없이 안전하게 처리되고,
// 디코드→인코딩 왕복이 비트 단위로 정확히 보존되는지 탐색한다.
// `go test -fuzz=FuzzDecode -fuzztime=30s`로 심화 실행, 평소엔 시드만 돈다.
func FuzzDecode(f *testing.F) {
	f.Add([]byte{})
	f.Add([]byte{0, 0, 0x80, 0x3f})
	f.Add([]byte{1, 2, 3})
	f.Add([]byte{0xff, 0xff, 0xff, 0x7f, 0, 0, 0, 0})
	f.Fuzz(func(t *testing.T, data []byte) {
		v, err := Decode(data)
		if err != nil {
			if len(data)%4 == 0 {
				t.Fatalf("4바이트 정렬 입력은 성공해야 한다: %v", err)
			}
			return
		}
		if len(v) != len(data)/4 {
			t.Fatalf("길이 불일치: %d != %d", len(v), len(data)/4)
		}
		if round := Encode(v); !bytes.Equal(round, data) {
			t.Fatalf("왕복 비트 보존 실패: %v != %v", round, data)
		}
	})
}
