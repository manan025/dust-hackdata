package controllers

import (
	"encoding/json"
	"hackdata/state"
	"log/slog"
	"net/http"
)

type Controllers struct {
	state  *state.State
	logger *slog.Logger
}

func New(st *state.State, logger *slog.Logger) *Controllers {
	if st == nil {
		st = &state.State{}
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Controllers{
		state:  st,
		logger: logger,
	}
}

func (c *Controllers) API(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"endpoints": []map[string]string{
			{
				"method":      http.MethodPost,
				"path":        "/api/run_pipeline",
				"description": "Download a git repo or zip into /tmp, run tests and perf profiling in Docker.",
			},
		},
	})
}

func (c *Controllers) Test(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
