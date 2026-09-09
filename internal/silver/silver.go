// Package silver는 bronze 원본 레코드를 통합 스키마로 정제하는 순수 함수들이다.
// 원본 pipeline/silver.py와 동일한 필드 매핑·텍스트 정리·full_text 합성을 수행한다.
package silver

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"regexp"
	"strconv"
	"strings"

	"github.com/Chae-JS/mentoai/internal/domain"
)

var (
	tagRe   = regexp.MustCompile(`<[^>]+>`)
	spaceRe = regexp.MustCompile(`\s+`)
)

// CleanText는 HTML 태그 제거 + 공백 정규화. 비면 nil.
func CleanText(value any) *string {
	if value == nil {
		return nil
	}
	text := spaceRe.ReplaceAllString(tagRe.ReplaceAllString(fmt.Sprint(value), " "), " ")
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return nil
	}
	return &trimmed
}

// payload 접근 헬퍼: JSON 디코딩 값(any)에서 타입별로 안전하게 꺼낸다.
func get(m map[string]any, keys ...string) any {
	var cur any = m
	for _, k := range keys {
		asMap, ok := cur.(map[string]any)
		if !ok {
			return nil
		}
		cur = asMap[k]
	}
	return cur
}

func str(m map[string]any, keys ...string) *string {
	return CleanText(get(m, keys...))
}

func rawStr(m map[string]any, keys ...string) string {
	if v := get(m, keys...); v != nil {
		s, _ := v.(string)
		return s
	}
	return ""
}

// idOf는 JSON 원시값(문자열·숫자)을 문자열 식별자로 바꾼다.
// Python의 str(payload.get(key))에 해당한다.
func idOf(m map[string]any, keys ...string) string {
	v := get(m, keys...)
	switch n := v.(type) {
	case string:
		return n
	case float64:
		if n == float64(int64(n)) {
			return strconv.FormatInt(int64(n), 10)
		}
		return fmt.Sprint(n)
	case nil:
		return ""
	default:
		return fmt.Sprint(n)
	}
}

func num(m map[string]any, keys ...string) *int {
	v := get(m, keys...)
	switch n := v.(type) {
	case float64:
		i := int(n)
		return &i
	case int:
		return &n
	case json.Number:
		if i, err := n.Int64(); err == nil {
			out := int(i)
			return &out
		}
	}
	return nil
}

func boolean(m map[string]any, keys ...string) *bool {
	if v, ok := get(m, keys...).(bool); ok {
		return &v
	}
	return nil
}

// NormalizeWanted는 Wanted 원본 payload를 통합 스키마로 매핑한다.
func NormalizeWanted(record domain.RawRecord) (*domain.SilverRow, error) {
	var payload map[string]any
	if err := json.Unmarshal(record.Payload, &payload); err != nil {
		return nil, err
	}
	sourceID := idOf(payload, "id")
	if sourceID == "" {
		sourceID = record.SourceID
	}
	if sourceID == "" {
		return nil, nil
	}
	dueTime := rawStr(payload, "due_time")
	if dueTime == "" {
		dueTime = "상시채용"
	}
	var skillTags []string
	if tags, ok := get(payload, "skill_tags").([]any); ok {
		for _, t := range tags {
			if t == nil {
				continue
			}
			s := fmt.Sprint(t)
			if s != "" {
				skillTags = append(skillTags, s)
			}
		}
	}
	return &domain.SilverRow{
		Source:         "wanted",
		SourceID:       sourceID,
		Company:        str(payload, "company", "name"),
		Position:       str(payload, "detail", "position"),
		Location:       str(payload, "address", "full_location"),
		Intro:          str(payload, "detail", "intro"),
		MainTasks:      str(payload, "detail", "main_tasks"),
		Requirements:   str(payload, "detail", "requirements"),
		PreferredPoint: str(payload, "detail", "preferred_points"),
		Benefits:       str(payload, "detail", "benefits"),
		EmploymentType: str(payload, "employment_type"),
		IsNewbie:       boolean(payload, "is_newbie"),
		AnnualFrom:     num(payload, "annual_from"),
		AnnualTo:       num(payload, "annual_to"),
		DueTime:        dueTime,
		SkillTags:      skillTags,
		Pay:            nil,
		Link:           nil,
		Deadline:       nil,
		CollectedAt:    record.CollectedAt,
	}, nil
}

// NormalizeWork24는 work24 원본 payload를 통합 스키마로 매핑한다.
func NormalizeWork24(record domain.RawRecord) (*domain.SilverRow, error) {
	var payload map[string]any
	if err := json.Unmarshal(record.Payload, &payload); err != nil {
		return nil, err
	}
	sourceID := idOf(payload, "source_id")
	if sourceID == "" {
		sourceID = record.SourceID
	}
	if sourceID == "" {
		return nil, nil
	}
	dueTime := rawStr(payload, "deadline")
	if dueTime == "" {
		dueTime = "채용시까지"
	}
	return &domain.SilverRow{
		Source:         "work24",
		SourceID:       sourceID,
		Company:        str(payload, "company"),
		Position:       str(payload, "title"),
		Location:       str(payload, "location"),
		Intro:          nil,
		MainTasks:      str(payload, "description"),
		Requirements:   str(payload, "requirements"),
		PreferredPoint: str(payload, "preferred"),
		Benefits:       nil,
		EmploymentType: nil,
		IsNewbie:       nil,
		AnnualFrom:     nil,
		AnnualTo:       nil,
		DueTime:        dueTime,
		SkillTags:      []string{},
		Pay:            str(payload, "pay"),
		Link:           str(payload, "link"),
		Deadline:       str(payload, "deadline"),
		CollectedAt:    record.CollectedAt,
	}, nil
}

var normalizers = map[string]func(domain.RawRecord) (*domain.SilverRow, error){
	"wanted": NormalizeWanted,
	"work24": NormalizeWork24,
}

// BuildFullText는 임베딩 입력용 단일 문서 텍스트를 합성한다.
func BuildFullText(row domain.SilverRow) string {
	var parts []string
	if row.Company != nil {
		parts = append(parts, fmt.Sprintf("[회사] %s", *row.Company))
	}
	if row.Position != nil {
		parts = append(parts, fmt.Sprintf("[포지션] %s", *row.Position))
	}
	if row.AnnualFrom != nil || row.AnnualTo != nil {
		from, to := 0, 0
		if row.AnnualFrom != nil {
			from = *row.AnnualFrom
		}
		if row.AnnualTo != nil {
			to = *row.AnnualTo
		}
		parts = append(parts, fmt.Sprintf("[경력요건] %d년 ~ %d년", from, to))
	}
	if row.IsNewbie != nil && *row.IsNewbie {
		parts = append(parts, "[신입 가능]")
	}
	if len(row.SkillTags) > 0 {
		parts = append(parts, fmt.Sprintf("[기술스택] %s", strings.Join(row.SkillTags, ", ")))
	}
	if row.MainTasks != nil {
		parts = append(parts, fmt.Sprintf("[주요업무] %s", *row.MainTasks))
	}
	if row.Requirements != nil {
		parts = append(parts, fmt.Sprintf("[자격요건] %s", *row.Requirements))
	}
	if row.PreferredPoint != nil {
		parts = append(parts, fmt.Sprintf("[우대사항] %s", *row.PreferredPoint))
	}
	if row.Location != nil {
		parts = append(parts, fmt.Sprintf("[위치] %s", *row.Location))
	}
	return strings.Join(parts, "\n")
}

// Build는 bronze 레코드 전체를 정제·중복제거(keep-last)한다.
// Polars unique(subset=[source, source_id], keep="last", maintain_order=True)와
// 동일하게, 각 키의 마지막 등장 위치에 마지막 내용을 남긴다.
func Build(records []domain.RawRecord) []domain.SilverRow {
	var normalized []domain.SilverRow
	for _, record := range records {
		normalize, ok := normalizers[record.Source]
		if !ok {
			slog.Warn("알 수 없는 소스", "source", record.Source)
			continue
		}
		row, err := normalize(record)
		if err != nil {
			slog.Warn("정제 실패", "source", record.Source, "source_id", record.SourceID, "error", err)
			continue
		}
		// 회사/포지션이 모두 없는 레코드는 쓸모 없다
		if row != nil && (isSet(row.Company) || isSet(row.Position)) {
			row.FullText = BuildFullText(*row)
			normalized = append(normalized, *row)
		}
	}

	// keep-last dedup: 뒤에서부터 first-seen만 남기고 뒤집는다.
	seen := make(map[string]struct{}, len(normalized))
	out := make([]domain.SilverRow, 0, len(normalized))
	for i := len(normalized) - 1; i >= 0; i-- {
		row := normalized[i]
		key := row.Source + "\x00" + row.SourceID
		if _, dup := seen[key]; dup {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, row)
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out
}

func isSet(s *string) bool { return s != nil && *s != "" }
