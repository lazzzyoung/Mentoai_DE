package api

import (
	"net/http"

	"github.com/Chae-JS/mentoai/internal/domain"
)

// listUsers는 GET /api/v1/users 다.
func (s *Server) listUsers(w http.ResponseWriter, r *http.Request) {
	if s.authRequired {
		id, _, _ := s.auth.Authenticated(r)
		if !s.adminIDs[id] {
			user, err := s.auth.Me(r.Context(), id)
			if err != nil {
				s.writeError(w, r, err)
				return
			}
			writeJSON(w, http.StatusOK, []domain.UserSummary{{ID: user.ID, Username: user.Username, DesiredJob: user.DesiredJob, CareerYears: user.CareerYears}})
			return
		}
	}
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
	if !s.canAccessUser(w, r, userID) {
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
	if !s.canAccessUser(w, r, userID) {
		return
	}
	result, err := s.ana.Analyze(r.Context(), jobID, userID)
	if err != nil {
		s.writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}
