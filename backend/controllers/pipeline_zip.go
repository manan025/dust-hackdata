package controllers

import (
	"archive/zip"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const (
	zipDownloadTimeout = 30 * time.Second
	maxZipBytes        = int64(200 << 20)
	maxZipEntryBytes   = int64(200 << 20)
	maxUnzipBytes      = int64(500 << 20)
)

func isZipURL(raw string) bool {
	return strings.HasSuffix(strings.ToLower(raw), ".zip")
}

func downloadAndExtractZip(rawURL, destDir string) error {
	client := &http.Client{Timeout: zipDownloadTimeout}
	resp, err := client.Get(rawURL)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return &httpError{status: resp.StatusCode}
	}
	if resp.ContentLength > maxZipBytes && resp.ContentLength != -1 {
		return &zipSizeError{kind: "download", size: resp.ContentLength}
	}

	zipPath := filepath.Join(destDir, "archive.zip")
	out, err := os.Create(zipPath)
	if err != nil {
		return err
	}
	limited := io.LimitReader(resp.Body, maxZipBytes+1)
	written, err := io.Copy(out, limited)
	if err != nil {
		_ = out.Close()
		return err
	}
	if written > maxZipBytes {
		_ = out.Close()
		return &zipSizeError{kind: "download", size: written}
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

	var total int64
	for _, file := range reader.File {
		if err := extractZipFile(file, destDir, &total); err != nil {
			return err
		}
	}
	return nil
}

func extractZipFile(file *zip.File, destDir string, total *int64) error {
	targetPath := filepath.Join(destDir, file.Name)
	cleanTarget := filepath.Clean(targetPath)
	if !strings.HasPrefix(cleanTarget, filepath.Clean(destDir)+string(os.PathSeparator)) {
		return &zipSlipError{path: file.Name}
	}

	if file.FileInfo().IsDir() {
		return os.MkdirAll(cleanTarget, 0o755)
	}

	declaredSize := int64(file.UncompressedSize64)
	if declaredSize > maxZipEntryBytes {
		return &zipSizeError{kind: "entry", size: declaredSize}
	}
	if total != nil && declaredSize > 0 && *total+declaredSize > maxUnzipBytes {
		return &zipSizeError{kind: "total", size: *total + declaredSize}
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

	limited := io.LimitReader(in, maxZipEntryBytes+1)
	written, err := io.Copy(out, limited)
	if err != nil {
		return err
	}
	if written > maxZipEntryBytes {
		return &zipSizeError{kind: "entry", size: written}
	}
	if total != nil {
		if *total+written > maxUnzipBytes {
			return &zipSizeError{kind: "total", size: *total + written}
		}
		*total += written
	}
	return nil
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

type zipSizeError struct {
	kind string
	size int64
}

func (e *zipSizeError) Error() string {
	return "zip size limit exceeded (" + e.kind + "): " + strconv.FormatInt(e.size, 10)
}
