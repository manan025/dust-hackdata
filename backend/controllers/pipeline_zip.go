package controllers

import (
	"archive/zip"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

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
