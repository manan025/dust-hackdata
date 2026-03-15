package controllers

import (
	"os"
	"os/exec"
	"path/filepath"
)

func gitClone(repoURL, destDir string) error {
	cmd := exec.Command("git", "clone", "--depth", "1", repoURL, destDir)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
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
