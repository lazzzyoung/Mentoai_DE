package silver

import (
	"testing"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

func rawRecord(source, sourceID string, payload string) domain.RawRecord {
	return domain.RawRecord{
		Source:      source,
		SourceID:    sourceID,
		CollectedAt: time.Date(2026, 9, 1, 9, 0, 0, 0, time.UTC).Format(time.RFC3339Nano),
		Payload:     []byte(payload),
	}
}

func TestCleanText(t *testing.T) {
	if got := CleanText("<b>hello</b>\t world \n"); got == nil || *got != "hello world" {
		t.Fatalf("got=%v", got)
	}
	if got := CleanText("   "); got != nil {
		t.Fatalf("공백만 있으면 nil: %v", got)
	}
	if got := CleanText(nil); got != nil {
		t.Fatalf("nil은 nil: %v", got)
	}
}

func TestNormalizeWanted(t *testing.T) {
	record := rawRecord("wanted", "1", `{
		"id": 123,
		"company": {"name": "테스트 주식회사"},
		"address": {"full_location": "서울 강남구"},
		"employment_type": "정규직",
		"is_newbie": true,
		"annual_from": 3,
		"annual_to": 100,
		"skill_tags": ["Python", "SQL", null],
		"detail": {
			"position": "데이터 엔지니어",
			"intro": "<p>회사 소개</p>",
			"main_tasks": "파이프라인 구축",
			"requirements": "3년 이상"
		}
	}`)

	row, err := NormalizeWanted(record)
	if err != nil {
		t.Fatal(err)
	}
	if row.SourceID != "123" || *row.Company != "테스트 주식회사" {
		t.Fatalf("기본 매핑 실패: %+v", row)
	}
	if row.Intro == nil || *row.Intro != "회사 소개" {
		t.Fatalf("HTML 태그 제거 실패: %v", row.Intro)
	}
	if row.IsNewbie == nil || !*row.IsNewbie {
		t.Fatal("is_newbie 실패")
	}
	if row.AnnualFrom == nil || *row.AnnualFrom != 3 || row.AnnualTo == nil || *row.AnnualTo != 100 {
		t.Fatalf("연봉 매핑 실패: %v %v", row.AnnualFrom, row.AnnualTo)
	}
	if row.DueTime != "상시채용" {
		t.Fatalf("기본 due_time: %q", row.DueTime)
	}
	if len(row.SkillTags) != 2 {
		t.Fatalf("null 태그 제외: %v", row.SkillTags)
	}
	if row.Pay != nil || row.Link != nil {
		t.Fatal("wanted는 pay/link가 항상 비어 있다")
	}
}

func TestNormalizeWork24(t *testing.T) {
	record := rawRecord("work24", "K1234567890", `{
		"source_id": "K1234567890",
		"company": "정부 공공기관",
		"title": "정보화 사업",
		"location": "대전 유성구",
		"description": "업무 내용",
		"pay": "연봉 5000만원",
		"deadline": "2026-09-30"
	}`)

	row, err := NormalizeWork24(record)
	if err != nil {
		t.Fatal(err)
	}
	if *row.Position != "정보화 사업" || row.MainTasks == nil || *row.MainTasks != "업무 내용" {
		t.Fatalf("매핑 실패: %+v", row)
	}
	if row.DueTime != "2026-09-30" || row.Deadline == nil || *row.Deadline != "2026-09-30" {
		t.Fatalf("마감일 매핑 실패: %q", row.DueTime)
	}
	if row.SkillTags == nil || len(row.SkillTags) != 0 {
		t.Fatal("work24는 기술스택이 비어 있다")
	}
	if row.AnnualFrom != nil {
		t.Fatal("work24는 경력 연수가 없다")
	}
}

func TestBuildFullTextSections(t *testing.T) {
	from := 1
	row := domain.SilverRow{
		Company:    strptr("ACME"),
		Position:   strptr("엔지니어"),
		AnnualFrom: &from,
		SkillTags:  []string{"Go"},
		MainTasks:  strptr("개발"),
	}
	got := BuildFullText(row)
	want := "[회사] ACME\n[포지션] 엔지니어\n[경력요건] 1년 ~ 0년\n[기술스택] Go\n[주요업무] 개발"
	if got != want {
		t.Fatalf("got=%q want=%q", got, want)
	}
}

func TestBuildDedupKeepsLast(t *testing.T) {
	records := []domain.RawRecord{
		rawRecord("wanted", "1", `{"id": 1, "company": {"name": "첫버전"}, "detail": {"position": "A"}}`),
		rawRecord("work24", "2", `{"source_id": "K2", "title": "B"}`),
		rawRecord("wanted", "1", `{"id": 1, "company": {"name": "갱신됨"}, "detail": {"position": "A2"}}`),
		rawRecord("unknown", "3", `{}`), // 알 수 없는 소스는 건너뜀
	}

	rows := Build(records)
	if len(rows) != 2 {
		t.Fatalf("중복제거 실패: %d rows", len(rows))
	}
	// keep-last: 각 키의 마지막 등장 위치에 마지막 내용이 남는다.
	if rows[0].SourceID != "K2" {
		t.Fatalf("순서 유지 실패: %+v", rows[0])
	}
	if rows[1].Company == nil || *rows[1].Company != "갱신됨" {
		t.Fatalf("keep-last 실패: %+v", rows[1])
	}
	if rows[1].FullText == "" {
		t.Fatal("full_text가 합성되어야 한다")
	}
}

func TestBuildDropsCompanyAndPositionless(t *testing.T) {
	rows := Build([]domain.RawRecord{rawRecord("wanted", "1", `{"id": 1}`)})
	if len(rows) != 0 {
		t.Fatalf("회사/포지션 모두 없으면 버린다: %d", len(rows))
	}
}

func strptr(s string) *string { return &s }
