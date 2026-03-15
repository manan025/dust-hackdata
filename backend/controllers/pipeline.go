package controllers

import (
	"encoding/json"
	"fmt"
	"hackdata/config"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

type runPipelineRequest struct {
	URL        string `json:"url"`
	Commit     string `json:"commit"`
	BaseBranch string `json:"base_branch"`
	RepoOwner  string `json:"repo_owner"`
	RepoName   string `json:"repo_name"`
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

	result, status, err := c.runPipeline(req)
	if err != nil {
		http.Error(w, err.Error(), status)
		return
	}
	if strings.TrimSpace(req.Commit) != "" {
		writeJSON(w, http.StatusOK, map[string]string{
			"pr_url": result.PullRequestURL,
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"output": result.Output,
		"zip":    result.ZipURL,
	})
}

type pipelineResult struct {
	RepoDir        string
	ArtifactsDir   string
	LogPath        string
	Output         string
	ZipURL         string
	PullRequestURL string
}

func (c *Controllers) runPipeline(req runPipelineRequest) (pipelineResult, int, error) {
	var result pipelineResult

	workdir, err := os.MkdirTemp("/tmp", "hackdata-")
	if err != nil {
		c.logger.Error("failed to create temp dir", "error", err)
		return result, http.StatusInternalServerError, fmt.Errorf("failed to create temp dir")
	}

	if isZipURL(req.URL) {
		if err := downloadAndExtractZip(req.URL, workdir); err != nil {
			c.logger.Error("failed to download zip", "url", req.URL, "error", err)
			return result, http.StatusBadRequest, fmt.Errorf("failed to download zip")
		}
	} else {
		dest := filepath.Join(workdir, "repo")
		if err := gitClone(req.URL, dest); err != nil {
			c.logger.Error("failed to clone repo", "url", req.URL, "error", err)
			return result, http.StatusBadRequest, fmt.Errorf("failed to clone repo")
		}
	}

	repoDir, err := detectRepoDir(workdir)
	if err != nil {
		c.logger.Error("failed to detect repo dir", "workdir", workdir, "error", err)
		return result, http.StatusInternalServerError, fmt.Errorf("failed to detect repo dir")
	}
	if commit := strings.TrimSpace(req.Commit); commit != "" {
		if _, err := os.Stat(filepath.Join(repoDir, ".git")); err != nil {
			return result, http.StatusBadRequest, fmt.Errorf("commit reset requires a git repo")
		}
		if err := gitResetHard(repoDir, commit); err != nil {
			c.logger.Error("failed to reset to commit", "commit", commit, "error", err)
			return result, http.StatusBadRequest, fmt.Errorf("failed to reset to commit")
		}
	}

	artifactsDir := filepath.Join(workdir, "artifacts")
	if err := os.MkdirAll(artifactsDir, 0o755); err != nil {
		c.logger.Error("failed to create artifacts dir", "error", err)
		return result, http.StatusInternalServerError, fmt.Errorf("failed to create artifacts dir")
	}

	repoRoot, err := findRepoRoot()
	if err != nil {
		c.logger.Error("failed to locate repo root", "error", err)
		return result, http.StatusInternalServerError, fmt.Errorf("failed to locate repo root")
	}
	if err := ensureDockerImage(repoRoot, c.logger); err != nil {
		c.logger.Error("failed to build docker image", "error", err)
		return result, http.StatusInternalServerError, fmt.Errorf("failed to build docker image")
	}

	logPath := filepath.Join(artifactsDir, "pipeline.log")
	c.logger.Info("pipeline log path", "path", logPath)
	logFile, err := os.Create(logPath)
	if err != nil {
		c.logger.Error("failed to create log file", "error", err)
		return result, http.StatusInternalServerError, fmt.Errorf("failed to create log file")
	}
	defer logFile.Close()

	args := []string{
		"run",
		"--rm",
		"--privileged",
		"--cap-add", "PERFMON",
		"--security-opt", "seccomp=unconfined",
		"-e", "PERF_RECOMMENDATIONS=" + strconv.Itoa(config.PerfLoops),
	}
	if apiKey := os.Getenv("OPENAI_API_KEY"); apiKey != "" {
		args = append(args, "-e", "OPENAI_API_KEY="+apiKey)
	}
	if supabaseURL := os.Getenv("SUPABASE_URL"); supabaseURL != "" {
		args = append(args, "-e", "SUPABASE_URL="+supabaseURL)
	}
	if supabaseKey := os.Getenv("SUPABASE_SERVICE_ROLE_KEY"); supabaseKey != "" {
		args = append(args, "-e", "SUPABASE_SERVICE_ROLE_KEY="+supabaseKey)
	}
	if supabaseBucket := os.Getenv("SUPABASE_SOURCE_BUCKET"); supabaseBucket != "" {
		args = append(args, "-e", "SUPABASE_SOURCE_BUCKET="+supabaseBucket)
	}
	args = append(
		args,
		"-v", fmt.Sprintf("%s:/work", repoDir),
		"-v", fmt.Sprintf("%s:/out", artifactsDir),
		dockerImage,
		"/runner/run_in_container.sh",
		"/work",
	)
	runCmd := exec.Command("docker", args...)
	runCmd.Stdout = logFile
	runCmd.Stderr = logFile
	if err := runCmd.Run(); err != nil {
		c.logger.Error("pipeline execution failed", "error", err, "log", logPath)
		return result, http.StatusInternalServerError, fmt.Errorf("pipeline execution failed; see artifacts log")
	}

	llmPath := filepath.Join(artifactsDir, "llm_output.txt")
	llmTail, err := readFileTail(llmPath, 20000)
	if err != nil && !os.IsNotExist(err) {
		c.logger.Error("failed to read llm output", "error", err)
	}

	uploadPath := filepath.Join(artifactsDir, "upload.json")
	zipURL, err := readUploadURL(uploadPath)
	if err != nil && !os.IsNotExist(err) {
		c.logger.Error("failed to read upload output", "error", err)
	}

	if llmTail == "" {
		llmTail, err = readFileTail(logPath, 20000)
		if err != nil {
			c.logger.Error("failed to read pipeline log", "error", err)
		}
	}

	result.RepoDir = repoDir
	result.ArtifactsDir = artifactsDir
	result.LogPath = logPath
	result.Output = llmTail
	result.ZipURL = zipURL

	if strings.TrimSpace(req.Commit) != "" {
		baseBranch := strings.TrimSpace(req.BaseBranch)
		prURL, err := c.commitAndOpenPRWithRepo(repoDir, req.Commit, baseBranch, req.RepoOwner, req.RepoName)
		if err != nil {
			return result, http.StatusInternalServerError, err
		}
		result.PullRequestURL = prURL
	}
	return result, http.StatusOK, nil
}

func readUploadURL(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	var payload struct {
		SignedURL string `json:"signed_url"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return "", err
	}
	return payload.SignedURL, nil
}

func gitResetHard(repoDir, commit string) error {
	verify := exec.Command("git", "-C", repoDir, "rev-parse", "--verify", commit)
	if err := verify.Run(); err != nil {
		fetch := exec.Command("git", "-C", repoDir, "fetch", "--depth", "1", "origin", commit)
		_ = fetch.Run()
	}
	reset := exec.Command("git", "-C", repoDir, "reset", "--hard", commit)
	reset.Stdout = os.Stdout
	reset.Stderr = os.Stderr
	return reset.Run()
}

func readFileTail(path string, maxBytes int64) (string, error) {
	if maxBytes <= 0 {
		return "", nil
	}
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return "", err
	}
	size := info.Size()
	if size == 0 {
		return "", nil
	}
	if maxBytes > size {
		maxBytes = size
	}
	if _, err := file.Seek(-maxBytes, io.SeekEnd); err != nil {
		return "", err
	}
	buf := make([]byte, maxBytes)
	n, err := io.ReadFull(file, buf)
	if err != nil && err != io.ErrUnexpectedEOF {
		return "", err
	}
	return string(buf[:n]), nil
}
