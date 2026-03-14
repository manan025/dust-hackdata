package server

import (
	"hackdata/controllers"
	"hackdata/state"
	"log/slog"
	"net/http"
)

type Mux struct {
	mux    *http.ServeMux
	state  *state.State
	logger *slog.Logger
}

func NewMux(st *state.State, logger *slog.Logger) *Mux {
	if st == nil {
		st = &state.State{}
	}
	if logger == nil {
		logger = slog.Default()
	}
	m := &Mux{
		mux:    http.NewServeMux(),
		state:  st,
		logger: logger,
	}
	m.routes()
	return m
}

func (m *Mux) routes() {
	ctrl := controllers.New(m.state, m.logger)
	m.mux.HandleFunc("/api", ctrl.API)
	m.mux.HandleFunc("/test", ctrl.Test)
	m.mux.HandleFunc("/api/run_pipeline", ctrl.RunPipeline)
}

func (m *Mux) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	m.mux.ServeHTTP(w, r)
}
