package api

import (
	"net/http"
)

// listUsers는 GET /api/v1/users 다.
func (s *Server) listUsers(w http.ResponseWriter, r *http.Request) {
	users, err := s.users.ListSummaries(r.Context())
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, users)
}

// recommendJobs는 POST /api/v1/jobs/recommend/{user_id} 다.
func (s *Server) recommendJobs(w http.ResponseWriter, r *http.Request) {
	userID, ok := pathInt(w, r, "user_id")
	if !ok {
		return
	}
	result, err := s.rec.Recommend(r.Context(), userID)
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// analyzeJob은 POST /api/v1/jobs/{job_id}/analyze/{user_id} 다.
func (s *Server) analyzeJob(w http.ResponseWriter, r *http.Request) {
	jobID, ok := pathInt(w, r, "job_id")
	if !ok {
		return
	}
	userID, ok := pathInt(w, r, "user_id")
	if !ok {
		return
	}
	result, err := s.ana.Analyze(r.Context(), jobID, userID)
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}
