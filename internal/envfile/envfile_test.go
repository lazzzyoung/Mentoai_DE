package envfile

import (
	"os"
	"path/filepath"
	"testing"
)

func TestUpdateReplacesInPlaceAndPreservesComments(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), ".env")
	original := "# 주석\nEMBEDDING_PROVIDER=fastembed\nSCHEDULE_ENABLED=false\nEMBEDDING_DIM=1024\n"
	if err := os.WriteFile(path, []byte(original), 0o644); err != nil {
		t.Fatal(err)
	}

	backup, err := Update(path, map[string]string{
		"EMBEDDING_PROVIDER": "gemini",
		"EMBEDDING_DIM":      "1024",
	})
	if err != nil {
		t.Fatal(err)
	}
	if backup == "" {
		t.Fatal("백업 파일이 생성되어야 한다")
	}

	raw, _ := os.ReadFile(path)
	got := string(raw)
	want := "# 주석\nEMBEDDING_PROVIDER=gemini\nSCHEDULE_ENABLED=false\nEMBEDDING_DIM=1024\n"
	if got != want {
		t.Fatalf("갱신 결과 불일치:\n got=%q\nwant=%q", got, want)
	}
}

func TestUpdateAppendsMissingKeys(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), ".env")
	if err := os.WriteFile(path, []byte("A=1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := Update(path, map[string]string{"B": "2", "A": "9"}); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(path)
	want := "A=9\nB=2\n"
	if string(raw) != want {
		t.Fatalf("추가 결과 불일치: got=%q want=%q", raw, want)
	}
}

func TestUpdateCreatesMissingFileWithoutBackup(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), ".env")
	backup, err := Update(path, map[string]string{"K": "V"})
	if err != nil {
		t.Fatal(err)
	}
	if backup != "" {
		t.Fatalf("원본이 없으면 백업 경로가 빈 문자열이어야 한다: %q", backup)
	}
	raw, _ := os.ReadFile(path)
	if string(raw) != "K=V\n" {
		t.Fatalf("생성 결과 불일치: %q", raw)
	}
}

func TestHasKeyIgnoresComments(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), ".env")
	_ = os.WriteFile(path, []byte("# GOOGLE_API_KEY=commented\nGOOGLE_API_KEY=real\n"), 0o644)
	if !HasKey(path, "GOOGLE_API_KEY") {
		t.Fatal("실제 키가 있어야 한다")
	}
	if HasKey(path, "OTHER") {
		t.Fatal("없는 키가 참이면 안 된다")
	}
}

func TestLoadSetsUnsetEnvOnly(t *testing.T) {
	path := filepath.Join(t.TempDir(), ".env")
	_ = os.WriteFile(path, []byte("MENTOAI_TEST_A=1\nMENTOAI_TEST_B=2\n"), 0o644)
	t.Setenv("MENTOAI_TEST_B", "existing")

	if err := Load(path); err != nil {
		t.Fatal(err)
	}
	if got := os.Getenv("MENTOAI_TEST_A"); got != "1" {
		t.Fatalf("MENTOAI_TEST_A=%q", got)
	}
	if got := os.Getenv("MENTOAI_TEST_B"); got != "existing" {
		t.Fatalf("기존 환경변수가 우선해야 한다: %q", got)
	}
}
