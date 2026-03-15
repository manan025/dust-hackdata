package controllers

import (
	"context"
	"fmt"
	"hackdata/config"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

const dockerImage = "hackdata-runner:latest"
const dockerBuildTimeout = 30 * time.Minute

func ensureDockerImage(repoRoot string, logger *slog.Logger) error {
	if !config.RebuildImage {
		check := exec.Command("docker", "image", "inspect", dockerImage)
		if err := check.Run(); err == nil {
			return nil
		}
	}

	dockerfile := filepath.Join(repoRoot, "Dockerfile")
	ctx, cancel := context.WithTimeout(context.Background(), dockerBuildTimeout)
	defer cancel()
	build := exec.CommandContext(ctx, "docker", "build", "-t", dockerImage, "-f", dockerfile, repoRoot)
	build.Stdout = os.Stdout
	build.Stderr = os.Stderr
	logger.Info("building docker image", "image", dockerImage)
	if err := build.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("docker build timed out after %s", dockerBuildTimeout)
		}
		return err
	}
	return nil
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
