package scrapers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"

	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
)

const (
	work24ListURL   = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"
	work24DetailURL = "https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do"

	work24ListParams = "occupation=135101,135102,136102,026,024&resultCnt=50&sortField=DATE&sortOrderBy=DESC&pageIndex=1&siteClcd=all"
)

var (
	work24AuthRe  = regexp.MustCompile(`wantedAuthNo=([a-zA-Z0-9]+)`)
	work24KRe     = regexp.MustCompile(`(K\d{10,})`)
	work24RowIDRe = regexp.MustCompile(`^list\d+$`)
	work24RegRe   = regexp.MustCompile(`등록일\s?:\s?(\d{4}-\d{2}-\d{2})`)
	work24CloseRe = regexp.MustCompile(`마감일\s?:\s?(\d{4}-\d{2}-\d{2})`)
	work24SpaceRe = regexp.MustCompile(`\s+`)
)

// Work24는 work24(국민취업지원 포털) HTML을 파싱한다.
type Work24 struct {
	delaySeconds float64
	http         *http.Client
	rand         *rand.Rand
}

// NewWork24는 설정에서 work24 수집기를 만든다.
func NewWork24(s config.Settings) *Work24 {
	return &Work24{
		delaySeconds: s.ScrapeDelaySeconds,
		http:         &http.Client{Timeout: 15 * time.Second},
		rand:         rand.New(rand.NewSource(time.Now().UnixNano())),
	}
}

type work24ListRow struct {
	authNo   string
	company  string
	title    string
	pay      string
	location string
	regDate  string
	deadline string
}

// Scrape는 work24 공고를 수집해 bronze 레코드로 반환한다.
func (w *Work24) Scrape(ctx context.Context) ([]domain.RawRecord, error) {
	rows, err := w.fetchListRows(ctx)
	if err != nil {
		return nil, err
	}
	logf("work24: 리스트 %d행", len(rows))

	records := []domain.RawRecord{}
	for _, row := range rows {
		select {
		case <-ctx.Done():
			return records, ctx.Err()
		default:
		}

		parsed := parseListRow(row)
		if parsed == nil {
			continue
		}

		detail := w.fetchDetail(ctx, parsed.authNo)
		payload := map[string]string{
			"source_id":    parsed.authNo,
			"company":      parsed.company,
			"title":        parsed.title,
			"link":         work24DetailURL + "?wantedAuthNo=" + parsed.authNo,
			"pay":          parsed.pay,
			"location":     parsed.location,
			"reg_date":     parsed.regDate,
			"deadline":     parsed.deadline,
			"description":  detail["job_description"],
			"requirements": detail["requirements"],
			"preferred":    detail["preferred"],
		}
		raw, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		records = append(records, domain.RawRecord{
			Source:      "work24",
			SourceID:    parsed.authNo,
			CollectedAt: nowRFC3339(),
			Payload:     raw,
		})
		sleepJitter(ctx, w.rand, w.delaySeconds)
	}
	return records, nil
}

func (w *Work24) fetchListRows(ctx context.Context) ([]*goquery.Selection, error) {
	endpoint := work24ListURL + "?" + work24ListParams
	html, status, err := fetchHTML(ctx, w.http, endpoint)
	if err != nil {
		return nil, fmt.Errorf("work24 리스트 요청 실패: %w", err)
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("work24 리스트 요청 실패: %d", status)
	}
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return nil, err
	}
	var rows []*goquery.Selection
	doc.Find("tr").Each(func(_ int, s *goquery.Selection) {
		id, _ := s.Attr("id")
		if work24RowIDRe.MatchString(id) {
			rows = append(rows, s)
		}
	})
	return rows, nil
}

func (w *Work24) fetchDetail(ctx context.Context, authNo string) map[string]string {
	// 구조가 달라도 기본값을 반환한다.
	extracted := map[string]string{
		"job_description": "상세 내용 없음 (외부 채용 사이트 참조)",
		"requirements":    "학력/경력 무관",
		"preferred":       "우대사항 없음",
	}

	endpoint := work24DetailURL + "?wantedAuthNo=" + url.QueryEscape(authNo)
	html, status, err := fetchHTML(ctx, w.http, endpoint)
	if err != nil {
		logf("work24 상세 요청 실패(%s): %v", authNo, err)
		return map[string]string{"job_description": "상세 내용 없음", "requirements": "", "preferred": ""}
	}
	if status != http.StatusOK {
		return map[string]string{"job_description": "상세 내용 없음", "requirements": "", "preferred": ""}
	}
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return map[string]string{"job_description": "상세 내용 없음", "requirements": "", "preferred": ""}
	}
	parseDetailPage(doc, extracted)
	return extracted
}

// parseDetailPage는 상세 페이지에서 직무내용/자격/우대를 추출해 extracted를 갱신한다.
func parseDetailPage(doc *goquery.Document, extracted map[string]string) {
	contentArea := doc.Find("#contents")
	if contentArea.Length() == 0 {
		contentArea = doc.Find(".emp_detail")
	}
	if contentArea.Length() == 0 {
		return
	}

	contentArea.Find("th").EachWithBreak(func(_ int, th *goquery.Selection) bool {
		if goquery.NodeName(th) != "th" || !strings.Contains(th.Text(), "직무내용") {
			return true
		}
		if td := nextSibling(th, "td"); td.Length() > 0 {
			extracted["job_description"] = cleanSpace(td.Text())
		}
		return false
	})

	var reqList, prefList []string
	contentArea.Find("table").Each(func(_ int, table *goquery.Selection) {
		table.Find("tr").Each(func(_ int, tr *goquery.Selection) {
			th := tr.Find("th").First()
			td := tr.Find("td").First()
			if th.Length() == 0 || td.Length() == 0 {
				return
			}
			headerText, bodyText := cleanSpace(th.Text()), cleanSpace(td.Text())
			if bodyText == "" || strings.Contains(bodyText, "관계없음") ||
				strings.Contains(bodyText, "비희망") || strings.Contains(bodyText, "해당없음") {
				return
			}
			switch {
			case containsAny(headerText, "경력조건", "학력", "모집직종"):
				reqList = append(reqList, headerText+": "+bodyText)
			case containsAny(headerText, "우대조건", "전공", "자격면허", "외국어", "컴퓨터"):
				prefList = append(prefList, headerText+": "+bodyText)
			}
		})
	})
	if len(reqList) > 0 {
		extracted["requirements"] = strings.Join(reqList, " | ")
	}
	if len(prefList) > 0 {
		extracted["preferred"] = strings.Join(prefList, " | ")
	}
}

// parseListRow는 리스트 한 행을 파싱한다. 파싱 불가 행은 nil이다.
func parseListRow(row *goquery.Selection) *work24ListRow {
	html, _ := goquery.OuterHtml(row)

	authNo := ""
	if m := work24AuthRe.FindStringSubmatch(html); m != nil {
		authNo = m[1]
	} else if m := work24KRe.FindStringSubmatch(html); m != nil {
		authNo = m[1]
	} else {
		return nil
	}

	cols := row.Find("td")
	if cols.Length() < 3 {
		return nil
	}

	td0Parts := strings.Split(textPipe(cols.Eq(0)), "|")
	company := "N/A"
	if len(td0Parts) > 0 && strings.TrimSpace(td0Parts[0]) != "" {
		company = strings.TrimSpace(td0Parts[0])
	}
	title := "N/A"
	if len(td0Parts) > 1 {
		potential := strings.TrimSpace(td0Parts[1])
		if strings.Contains(potential, "입사지원") || strings.Contains(potential, "요약보기") {
			if len(td0Parts) > 2 {
				title = strings.TrimSpace(td0Parts[2])
			}
		} else {
			title = potential
		}
	}

	pay, location := "면접 후 결정", "지역 미상"
	for _, part := range strings.Split(textPipe(cols.Eq(1)), "|") {
		part = cleanSpace(part)
		if containsAny(part, "연봉", "월급", "시급") {
			pay = part
		} else if containsAny(part, "시 ", "구 ", "군 ") && !strings.Contains(part, "주") {
			location = part
		}
	}

	td2 := textPipe(cols.Eq(2))
	regDate := time.Now().UTC().Format("2006-01-02")
	if m := work24RegRe.FindStringSubmatch(td2); m != nil {
		regDate = m[1]
	}
	deadline := "채용시까지"
	if m := work24CloseRe.FindStringSubmatch(td2); m != nil {
		deadline = m[1]
	}

	return &work24ListRow{
		authNo:   authNo,
		company:  company,
		title:    title,
		pay:      pay,
		location: location,
		regDate:  regDate,
		deadline: deadline,
	}
}

// ---------- HTML 헬퍼 ----------

func fetchHTML(ctx context.Context, client *http.Client, endpoint string) (string, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", 0, err
	}
	req.Header.Set("User-Agent", userAgent)

	resp, err := client.Do(req)
	if err != nil {
		return "", 0, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", resp.StatusCode, err
	}
	return string(body), resp.StatusCode, nil
}

// textPipe는 get_text(separator="|", strip=True)와 동일하다:
// 모든 텍스트 노드를 trim하고 빈 것은 버린 뒤 "|"로 이어 붙인다.
func textPipe(s *goquery.Selection) string {
	var parts []string
	var walk func(sel *goquery.Selection)
	walk = func(sel *goquery.Selection) {
		sel.Contents().Each(func(_ int, child *goquery.Selection) {
			if goquery.NodeName(child) == "#text" {
				trimmed := strings.TrimSpace(child.Text())
				if trimmed != "" {
					parts = append(parts, trimmed)
				}
				return
			}
			walk(child)
		})
	}
	walk(s)
	return strings.Join(parts, "|")
}

// nextSibling은 find_next_sibling(tag)과 동일한 다음 형제 요소를 찾는다.
func nextSibling(s *goquery.Selection, tag string) *goquery.Selection {
	return s.NextAll().Filter(tag).First()
}

func cleanSpace(text string) string {
	return strings.TrimSpace(work24SpaceRe.ReplaceAllString(text, " "))
}

func containsAny(s string, keywords ...string) bool {
	for _, kw := range keywords {
		if strings.Contains(s, kw) {
			return true
		}
	}
	return false
}
