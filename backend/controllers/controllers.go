package controllers

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"hackdata/state"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
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

func isZipURL(raw string) bool {
	return strings.HasSuffix(strings.ToLower(raw), ".zip")
}

func downloadAndExtractZip(rawURL, destDir string) error {
	resp, err := http.Get(rawURL)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return &httpError{status: resp.StatusCode}
	}

	zipPath := filepath.Join(destDir, "archive.zip")
	out, err := os.Create(zipPath)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, resp.Body); err != nil {
		_ = out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}

	return unzip(zipPath, destDir)
}

func unzip(zipPath, destDir string) error {
	reader, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer reader.Close()

	for _, file := range reader.File {
		if err := extractZipFile(file, destDir); err != nil {
			return err
		}
	}
	return nil
}

func extractZipFile(file *zip.File, destDir string) error {
	targetPath := filepath.Join(destDir, file.Name)
	cleanTarget := filepath.Clean(targetPath)
	if !strings.HasPrefix(cleanTarget, filepath.Clean(destDir)+string(os.PathSeparator)) {
		return &zipSlipError{path: file.Name}
	}

	if file.FileInfo().IsDir() {
		return os.MkdirAll(cleanTarget, 0o755)
	}

	if err := os.MkdirAll(filepath.Dir(cleanTarget), 0o755); err != nil {
		return err
	}

	in, err := file.Open()
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(cleanTarget)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

func gitClone(repoURL, destDir string) error {
	cmd := exec.Command("git", "clone", "--depth", "1", repoURL, destDir)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

type httpError struct {
	status int
}

func (e *httpError) Error() string {
	return http.StatusText(e.status)
}

type zipSlipError struct {
	path string
}

func (e *zipSlipError) Error() string {
	return "invalid zip path: " + e.path
}

const dockerImage = "hackdata-runner:latest"

func ensureDockerImage(repoRoot string, logger *slog.Logger) error {
	check := exec.Command("docker", "image", "inspect", dockerImage)
	if err := check.Run(); err == nil {
		return nil
	}

	dockerfile := filepath.Join(repoRoot, "Dockerfile")
	build := exec.Command("docker", "build", "-t", dockerImage, "-f", dockerfile, repoRoot)
	build.Stdout = os.Stdout
	build.Stderr = os.Stderr
	logger.Info("building docker image", "image", dockerImage)
	return build.Run()
}

func findRepoRoot() (string, error) {
	start, err := os.Getwd()
	if err != nil {
		return "", err
	}
	dir := start
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf("go.mod not found from %s", start)
		}
		dir = parent
	}
}

func detectRepoDir(workdir string) (string, error) {
	entries, err := os.ReadDir(workdir)
	if err != nil {
		return "", err
	}
	var (
		dirs  []string
		files int
	)
	for _, entry := range entries {
		if entry.IsDir() {
			dirs = append(dirs, entry.Name())
		} else {
			files++
		}
	}
	if files == 0 && len(dirs) == 1 {
		return filepath.Join(workdir, dirs[0]), nil
	}
	return workdir, nil
}
