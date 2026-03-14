package controllers

import (
	"fmt"
	"hackdata/config"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
)

const dockerImage = "hackdata-runner:latest"

func ensureDockerImage(repoRoot string, logger *slog.Logger) error {
	if !config.RebuildImage {
		check := exec.Command("docker", "image", "inspect", dockerImage)
		if err := check.Run(); err == nil {
			return nil
		}
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
