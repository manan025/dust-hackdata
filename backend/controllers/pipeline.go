package controllers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type runPipelineRequest struct {
	URL string `json:"url"`
}

func (c *Controllers) RunPipeline(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req runPipelineRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid json body", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(req.URL) == "" {
		http.Error(w, "url is required", http.StatusBadRequest)
		return
	}

	workdir, err := os.MkdirTemp("/tmp", "hackdata-")
	if err != nil {
		c.logger.Error("failed to create temp dir", "error", err)
		http.Error(w, "failed to create temp dir", http.StatusInternalServerError)
		return
	}

	if isZipURL(req.URL) {
		if err := downloadAndExtractZip(req.URL, workdir); err != nil {
			c.logger.Error("failed to download zip", "url", req.URL, "error", err)
			http.Error(w, "failed to download zip", http.StatusBadRequest)
			return
		}
	} else {
		dest := filepath.Join(workdir, "repo")
		if err := gitClone(req.URL, dest); err != nil {
			c.logger.Error("failed to clone repo", "url", req.URL, "error", err)
			http.Error(w, "failed to clone repo", http.StatusBadRequest)
			return
		}
	}

	repoDir, err := detectRepoDir(workdir)
	if err != nil {
		c.logger.Error("failed to detect repo dir", "workdir", workdir, "error", err)
		http.Error(w, "failed to detect repo dir", http.StatusInternalServerError)
		return
	}

	artifactsDir := filepath.Join(workdir, "artifacts")
	if err := os.MkdirAll(artifactsDir, 0o755); err != nil {
		c.logger.Error("failed to create artifacts dir", "error", err)
		http.Error(w, "failed to create artifacts dir", http.StatusInternalServerError)
		return
	}

	repoRoot, err := findRepoRoot()
	if err != nil {
		c.logger.Error("failed to locate repo root", "error", err)
		http.Error(w, "failed to locate repo root", http.StatusInternalServerError)
		return
	}
	if err := ensureDockerImage(repoRoot, c.logger); err != nil {
		c.logger.Error("failed to build docker image", "error", err)
		http.Error(w, "failed to build docker image", http.StatusInternalServerError)
		return
	}

	logPath := filepath.Join(artifactsDir, "pipeline.log")
	logFile, err := os.Create(logPath)
	if err != nil {
		c.logger.Error("failed to create log file", "error", err)
		http.Error(w, "failed to create log file", http.StatusInternalServerError)
		return
	}
	defer logFile.Close()

	runCmd := exec.Command(
		"docker",
		"run",
		"--rm",
		"--privileged",
		"--cap-add", "PERFMON",
		"--security-opt", "seccomp=unconfined",
		"-v", fmt.Sprintf("%s:/work", repoDir),
		"-v", fmt.Sprintf("%s:/out", artifactsDir),
		dockerImage,
		"/runner/run_in_container.sh",
		"/work",
	)
	runCmd.Stdout = logFile
	runCmd.Stderr = logFile
	if err := runCmd.Run(); err != nil {
		c.logger.Error("pipeline execution failed", "error", err, "log", logPath)
		http.Error(w, "pipeline execution failed; see artifacts log", http.StatusInternalServerError)
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{
		"workdir":    workdir,
		"repodir":    repoDir,
		"artifacts":  artifactsDir,
		"log_output": logPath,
	})
}
