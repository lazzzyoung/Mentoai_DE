// Package scrapers는 bronze 수집기들이다. 각 수집기는 Scraper 시그니처를 만족하며,
// 파이프라인에 주입된다. 실패는 오류로 반환하고 격리 판단은 파이프라인이 한다.
package scrapers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"time"

	"github.com/Chae-JS/mentoai/internal/config"
	"github.com/Chae-JS/mentoai/internal/domain"
)

// wanted는 Wanted 채용 JSON API를 사용한다.
type Wanted struct {
	baseURL      string
	groupID      string
	jobIDs       string
	maxItems     int
	delaySeconds float64
	http         *http.Client
	rand         *rand.Rand
}

// NewWanted는 설정에서 Wanted 수집기를 만든다.
func NewWanted(s config.Settings) *Wanted {
	return &Wanted{
		baseURL:      s.WantedBaseURL,
		groupID:      s.WantedJobGroupID,
		jobIDs:       s.WantedJobIDs,
		maxItems:     s.ScrapeMaxItems,
		delaySeconds: s.ScrapeDelaySeconds,
		http:         &http.Client{Timeout: 15 * time.Second},
		rand:         rand.New(rand.NewSource(time.Now().UnixNano())),
	}
}

const userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
	"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

type wantedListResponse struct {
	Data []struct {
		ID *int64 `json:"id"`
	} `json:"data"`
	Links struct {
		Next *string `json:"next"`
	} `json:"links"`
}

type wantedDetailResponse struct {
	Data struct {
		Job json.RawMessage `json:"job"`
	} `json:"data"`
}

// fetchJSON은 JSON API를 호출하고 응답 본문을 디코딩한다.
func fetchJSON(ctx context.Context, client *http.Client, endpoint string, out any) (int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("User-Agent", userAgent)

	resp, err := client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		io.Copy(io.Discard, resp.Body)
		return resp.StatusCode, nil
	}
	return resp.StatusCode, json.NewDecoder(resp.Body).Decode(out)
}

// Scrape는 Wanted 공고를 수집해 bronze 레코드로 반환한다.
func (w *Wanted) Scrape(ctx context.Context) ([]domain.RawRecord, error) {
	records := []domain.RawRecord{}
	ids, err := w.fetchJobIDs(ctx)
	if err != nil {
		return nil, err
	}

	logf("wanted: 수집 대상 %d건", len(ids))
	for _, jobID := range ids {
		select {
		case <-ctx.Done():
			return records, ctx.Err()
		default:
		}

		raw, err := w.fetchDetail(ctx, jobID)
		if err != nil {
			return nil, err
		}
		if raw != nil {
			records = append(records, domain.RawRecord{
				Source:      "wanted",
				SourceID:    fmt.Sprint(jobID),
				CollectedAt: nowRFC3339(),
				Payload:     raw,
			})
		}
		sleepJitter(ctx, w.rand, w.delaySeconds)
	}
	return records, nil
}

func (w *Wanted) fetchJobIDs(ctx context.Context) ([]int64, error) {
	var ids []int64
	offset := 0
	for len(ids) < w.maxItems {
		q := url.Values{}
		q.Set("job_group_id", w.groupID)
		q.Set("job_ids", w.jobIDs)
		q.Set("country", "kr")
		q.Set("job_sort", "job.popularity_order")
		q.Set("years", "-1")
		q.Set("locations", "all")
		q.Set("limit", "20")
		q.Set("offset", fmt.Sprint(offset))

		var data wantedListResponse
		status, err := fetchJSON(ctx, w.http, w.baseURL+"/api/chaos/navigation/v1/results?"+q.Encode(), &data)
		if err != nil {
			return nil, fmt.Errorf("wanted 리스트 요청 실패: %w", err)
		}
		if status != http.StatusOK {
			logf("wanted 리스트 요청 실패: %d", status)
			break
		}
		if len(data.Data) == 0 {
			break
		}
		for _, job := range data.Data {
			if job.ID != nil {
				ids = append(ids, *job.ID)
			}
		}
		if data.Links.Next == nil {
			break
		}
		offset += 20
		sleepJitter(ctx, w.rand, 0.4)
	}
	if len(ids) > w.maxItems {
		ids = ids[:w.maxItems]
	}
	return ids, nil
}

func (w *Wanted) fetchDetail(ctx context.Context, jobID int64) ([]byte, error) {
	endpoint := fmt.Sprintf("%s/api/chaos/jobs/v4/%d/details", w.baseURL, jobID)
	var data wantedDetailResponse
	status, err := fetchJSON(ctx, w.http, endpoint, &data)
	if err != nil {
		return nil, fmt.Errorf("wanted 상세 요청 실패 (ID: %d): %w", jobID, err)
	}
	if status == http.StatusNotFound {
		logf("wanted 공고 삭제/비공개 (ID: %d)", jobID)
		return nil, nil
	}
	if status != http.StatusOK {
		logf("wanted 상세 요청 실패: %d (ID: %d)", status, jobID)
		return nil, nil
	}
	if len(data.Data.Job) == 0 {
		return nil, nil
	}
	return data.Data.Job, nil
}
