package controllers

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strings"
)

type githubWebhookPR struct {
	Action     string `json:"action"`
	Repository struct {
		Owner struct {
			Login string `json:"login"`
		} `json:"owner"`
		Name string `json:"name"`
	} `json:"repository"`
	PullRequest struct {
		Head struct {
			SHA  string `json:"sha"`
			Repo struct {
				CloneURL string `json:"clone_url"`
			} `json:"repo"`
		} `json:"head"`
		Base struct {
			Ref string `json:"ref"`
		} `json:"base"`
	} `json:"pull_request"`
}

func (c *Controllers) GitHubWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	secret := os.Getenv("GITHUB_WEBHOOK_SECRET")
	if secret == "" {
		http.Error(w, "webhook secret not configured", http.StatusInternalServerError)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed to read body", http.StatusBadRequest)
		return
	}
	if !verifyGitHubSignature(body, r.Header.Get("X-Hub-Signature-256"), secret) {
		http.Error(w, "invalid signature", http.StatusUnauthorized)
		return
	}

	event := r.Header.Get("X-GitHub-Event")
	if event != "pull_request" {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	var payload githubWebhookPR
	if err := json.Unmarshal(body, &payload); err != nil {
		http.Error(w, "invalid payload", http.StatusBadRequest)
		return
	}
	if payload.Action != "opened" && payload.Action != "synchronize" && payload.Action != "reopened" {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	cloneURL := strings.TrimSpace(payload.PullRequest.Head.Repo.CloneURL)
	commit := strings.TrimSpace(payload.PullRequest.Head.SHA)
	base := strings.TrimSpace(payload.PullRequest.Base.Ref)
	if cloneURL == "" || commit == "" {
		http.Error(w, "missing repo or commit", http.StatusBadRequest)
		return
	}
	repoOwner := strings.TrimSpace(payload.Repository.Owner.Login)
	repoName := strings.TrimSpace(payload.Repository.Name)

	go func() {
		_, _, _ = c.runPipeline(runPipelineRequest{
			URL:        cloneURL,
			Commit:     commit,
			BaseBranch: base,
			RepoOwner:  repoOwner,
			RepoName:   repoName,
		})
	}()

	w.WriteHeader(http.StatusAccepted)
}

func verifyGitHubSignature(body []byte, signatureHeader, secret string) bool {
	if signatureHeader == "" {
		return false
	}
	const prefix = "sha256="
	if !strings.HasPrefix(signatureHeader, prefix) {
		return false
	}
	signature := strings.TrimPrefix(signatureHeader, prefix)
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(body)
	expected := hex.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(signature), []byte(expected))
}
