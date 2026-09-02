package scoring

import "testing"

func TestSimilarityToScore(t *testing.T) {
	cases := []struct {
		similarity float64
		want       int
	}{
		{0.87, 87},
		{1.5, 99},  // 상한 클램프
		{0.12, 40}, // 하한 클램프
		{1.0, 99},
	}
	for _, c := range cases {
		if got := SimilarityToScore(c.similarity); got != c.want {
			t.Errorf("SimilarityToScore(%v)=%d, want=%d", c.similarity, got, c.want)
		}
	}
}

func TestSkillOverlap(t *testing.T) {
	got := SkillOverlap(
		[]string{"python", " SQL ", "Java"},
		[]string{"Python", "sql", "Docker", ""},
	)
	if len(got) != 2 || got[0] != "python" || got[1] != " SQL " {
		t.Fatalf("대소문자 무시 일치 기대: %v", got)
	}
}

func TestBuildReason(t *testing.T) {
	annual := 5
	newbie := true
	got := BuildReason([]string{"Python"}, 2, []string{"Python", "SQL"}, &annual, nil)
	want := "보유 스킬(Python)이 포지션 기술스택과 일치, 경력 요건(5년+)까지 3년 부족."
	if got != want {
		t.Fatalf("got=%q want=%q", got, want)
	}

	got = BuildReason(nil, 0, nil, nil, &newbie)
	want = "희망 직무와 공고 문맥이 유사, 신입 지원 가능."
	if got != want {
		t.Fatalf("got=%q want=%q", got, want)
	}
}

func TestCareerLabel(t *testing.T) {
	from, to := 3, 7
	if got := CareerLabel(&from, &to, nil); got == nil || *got != "경력 3~7년" {
		t.Fatalf("got=%v", got)
	}
	highTo := 100
	if got := CareerLabel(&from, &highTo, nil); got == nil || *got != "경력 3년 이상" {
		t.Fatalf("상한 없음(100)은 '이상' 표기: %v", got)
	}
	if got := CareerLabel(nil, nil, nil); got != nil {
		t.Fatalf("경력 정보 없으면 nil: %v", got)
	}
	newbie := true
	if got := CareerLabel(&from, &to, &newbie); got == nil || *got != "신입 가능" {
		t.Fatalf("신입 우선: %v", got)
	}
}
