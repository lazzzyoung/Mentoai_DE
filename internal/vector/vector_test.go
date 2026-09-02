package vector

import (
	"bytes"
	"math"
	"testing"
)

func TestEncodeDecodeRoundtrip(t *testing.T) {
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
	if _, err := Decode([]byte{1, 2, 3}); err == nil {
		t.Fatal("4의 배수가 아닌 길이는 오류여야 한다")
	}
}

func TestCosine(t *testing.T) {
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
	b := Encode([]float32{1})
	if !bytes.Equal(b, []byte{0, 0, 0x80, 0x3f}) {
		t.Fatalf("little-endian float32 기대: %v", b)
	}
}
