package cmd

import (
	"flag"
	"fmt"
	"hackdata/config"
	"hackdata/server"
	"hackdata/state"
	"log/slog"
	"net/http"
	"os"
)

func Execute() {
	fs := flag.NewFlagSet(os.Args[0], flag.ExitOnError)
	fs.StringVar(&config.Addr, "addr", config.DefaultAddr, "address to listen on")
	fs.IntVar(&config.Port, "port", config.DefaultPort, "port to listen on")
	fs.StringVar(&config.LogLevel, "log-level", config.DefaultLogLevel, "log level (debug, info, warn, error)")
	fs.BoolVar(&config.RebuildImage, "rebuild-image", config.DefaultRebuildImage, "rebuild runner docker image on every pipeline run")
	fs.Parse(os.Args[1:])

	level := parseLogLevel(config.LogLevel)
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: level}))
	st := &state.State{}
	srv := server.NewMux(st, logger)
	addr := fmt.Sprintf("%s:%d", config.Addr, config.Port)
	logger.Info("starting server", "addr", addr)
	if err := http.ListenAndServe(addr, srv); err != nil {
		logger.Error("server stopped", "error", err)
		os.Exit(1)
	}

}

func parseLogLevel(level string) slog.Level {
	switch level {
	case "debug":
		return slog.LevelDebug
	case "warn":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
