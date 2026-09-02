package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// adminStats는 GET /api/v1/admin/stats 다.
func (s *Server) adminStats(w http.ResponseWriter, r *http.Request) {
	status, err := s.admin.Status(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, status)
}

// adminPipelineRuns는 GET /api/v1/admin/pipeline-runs 다.
func (s *Server) adminPipelineRuns(w http.ResponseWriter, r *http.Request) {
	runs, err := s.admin.ListRuns(r.Context(), 20)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, runs)
}

// adminTriggerPipeline은 POST /api/v1/admin/pipeline 다.
func (s *Server) adminTriggerPipeline(w http.ResponseWriter, r *http.Request) {
	if err := s.admin.TriggerPipeline(r.Context()); err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "started"})
}

// adminJobsList는 GET /api/v1/admin/jobs?query=&limit= 다.
func (s *Server) adminJobsList(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("query")
	limit := 30
	if raw := r.URL.Query().Get("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"detail": "limit은 정수여야 합니다"})
			return
		}
		limit = parsed
	}
	jobs, err := s.admin.ListJobs(r.Context(), query, limit)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, jobs)
}

// adminDeleteJob은 DELETE /api/v1/admin/jobs/{job_id} 다.
func (s *Server) adminDeleteJob(w http.ResponseWriter, r *http.Request) {
	jobID, ok := pathInt(w, r, "job_id")
	if !ok {
		return
	}
	if err := s.admin.DeleteJob(r.Context(), jobID); err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// decodeUserPayload는 요청 본문을 UserPayload로 읽는다. FastAPI처럼 본문 오류는 422다.
func decodeUserPayload(w http.ResponseWriter, r *http.Request) (domain.UserPayload, bool) {
	var p domain.UserPayload
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"detail": "요청 본문을 해석할 수 없습니다"})
		return p, false
	}
	return p, true
}

// adminCreateUser은 POST /api/v1/admin/users 다.
func (s *Server) adminCreateUser(w http.ResponseWriter, r *http.Request) {
	p, ok := decodeUserPayload(w, r)
	if !ok {
		return
	}
	user, err := s.admin.CreateUser(r.Context(), p)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, user)
}

// adminUpdateUser는 PUT /api/v1/admin/users/{user_id} 다.
func (s *Server) adminUpdateUser(w http.ResponseWriter, r *http.Request) {
	userID, ok := pathInt(w, r, "user_id")
	if !ok {
		return
	}
	p, ok := decodeUserPayload(w, r)
	if !ok {
		return
	}
	user, err := s.admin.UpdateUser(r.Context(), userID, p)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, user)
}

// adminDeleteUser는 DELETE /api/v1/admin/users/{user_id} 다.
func (s *Server) adminDeleteUser(w http.ResponseWriter, r *http.Request) {
	userID, ok := pathInt(w, r, "user_id")
	if !ok {
		return
	}
	if err := s.admin.DeleteUser(r.Context(), userID); err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// adminEmbeddingModels는 GET /api/v1/admin/embedding/models 다.
func (s *Server) adminEmbeddingModels(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, s.admin.EmbeddingModels())
}

// adminRebuildEmbeddings는 POST /api/v1/admin/embedding/rebuild 다.
func (s *Server) adminRebuildEmbeddings(w http.ResponseWriter, _ *http.Request) {
	if !s.admin.StartBackground("embedding_rebuild", func(ctx context.Context) error {
		_, err := s.admin.RebuildEmbeddings(ctx)
		return err
	}) {
		writeJSON(w, http.StatusConflict, map[string]string{"detail": "이미 실행 중입니다"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "started"})
}

// adminSwitchEmbedding은 POST /api/v1/admin/embedding/switch?provider=&model= 다.
func (s *Server) adminSwitchEmbedding(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	provider := q.Get("provider")
	if provider == "" {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"detail": "provider는 필수입니다"})
		return
	}
	model := q.Get("model")

	target, err := s.admin.ResolveEmbeddingTarget(provider, model, nil)
	if err != nil {
		writeError(w, err)
		return
	}
	if !s.admin.StartBackground("embedding_switch", func(ctx context.Context) error {
		_, err := s.admin.SwitchEmbeddingModel(ctx, provider, model, nil)
		return err
	}) {
		writeJSON(w, http.StatusConflict, map[string]string{"detail": "이미 실행 중입니다"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "started", "target": target.Key(), "dim": target.Dim})
}

// adminCacheList는 GET /api/v1/admin/cache 다.
func (s *Server) adminCacheList(w http.ResponseWriter, r *http.Request) {
	rows, err := s.admin.ListCache(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

// adminCacheClear는 DELETE /api/v1/admin/cache 다.
func (s *Server) adminCacheClear(w http.ResponseWriter, r *http.Request) {
	deleted, err := s.admin.ClearCache(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]int64{"deleted": deleted})
}

// adminCacheDelete는 DELETE /api/v1/admin/cache/{job_id}/{user_id} 다.
func (s *Server) adminCacheDelete(w http.ResponseWriter, r *http.Request) {
	jobID, ok := pathInt(w, r, "job_id")
	if !ok {
		return
	}
	userID, ok := pathInt(w, r, "user_id")
	if !ok {
		return
	}
	if err := s.admin.DeleteCache(r.Context(), jobID, userID); err != nil {
		writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
