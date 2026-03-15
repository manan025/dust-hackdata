package controllers

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

const gitCloneTimeout = 10 * time.Minute
const gitFetchTimeout = 5 * time.Minute

func gitClone(repoURL, destDir string) error {
	ctx, cancel := context.WithTimeout(context.Background(), gitCloneTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "git", "clone", "--depth", "1", repoURL, destDir)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func gitFetchCommit(repoDir, commit string) error {
	ctx, cancel := context.WithTimeout(context.Background(), gitFetchTimeout)
	defer cancel()
	fetch := exec.CommandContext(ctx, "git", "-C", repoDir, "fetch", "--depth", "1", "origin", commit)
	fetch.Stdout = os.Stdout
	fetch.Stderr = os.Stderr
	if err := fetch.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("git fetch timed out after %s", gitFetchTimeout)
		}
		return err
	}
	return nil
}

func gitCheckoutCommit(repoDir, commit string) error {
	ctx, cancel := context.WithTimeout(context.Background(), gitFetchTimeout)
	defer cancel()
	checkout := exec.CommandContext(ctx, "git", "-C", repoDir, "checkout", "--detach", commit)
	checkout.Stdout = os.Stdout
	checkout.Stderr = os.Stderr
	if err := checkout.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("git checkout timed out after %s", gitFetchTimeout)
		}
		return err
	}
	return nil
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
