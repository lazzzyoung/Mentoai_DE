// Package envfile은 .env 파일을 읽고 줄 보존 방식으로 갱신한다.
// 주석·순서·기타 키는 그대로 유지하고, 갱신 전 .bak 백업을 만든다.
package envfile

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Load는 .env의 KEY=VALUE를 환경변수로 올린다. 이미 설정된 환경변수가 우선하며,
// 파일이 없어도 오류가 아니다.
func Load(path string) error {
	lines, err := readLines(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	for _, line := range lines {
		key, value, ok := parseLine(line)
		if !ok {
			continue
		}
		if _, exists := os.LookupEnv(key); !exists {
			if err := os.Setenv(key, value); err != nil {
				return fmt.Errorf("환경변수 설정 실패 (%s): %w", key, err)
			}
		}
	}
	return nil
}

// Update는 키가 이미 있으면 해당 줄만 교체하고, 없으면 파일 끝에 추가한다.
// 백업 파일 경로를 반환한다(원본이 없었으면 빈 문자열).
func Update(path string, updates map[string]string) (string, error) {
	var lines []string
	backup := ""
	if _, err := os.Stat(path); err == nil {
		lines, err = readLines(path)
		if err != nil {
			return "", err
		}
		backupPath := path + ".bak"
		if err := copyFile(path, backupPath); err != nil {
			return "", fmt.Errorf(".env 백업 실패: %w", err)
		}
		backup = backupPath
	}

	output := make([]string, 0, len(lines)+len(updates))
	seen := make(map[string]struct{}, len(updates))
	for _, line := range lines {
		if key, _, ok := parseLine(line); ok {
			if newValue, replace := updates[key]; replace {
				output = append(output, key+"="+newValue)
				seen[key] = struct{}{}
				continue
			}
		}
		output = append(output, line)
	}
	for key, value := range updates {
		if _, exists := seen[key]; !exists {
			output = append(output, key+"="+value)
		}
	}

	if err := os.WriteFile(path, []byte(strings.Join(output, "\n")+"\n"), 0o644); err != nil {
		return "", err
	}
	return backup, nil
}

// HasKey는 주석 아닌 KEY=... 줄에 해당 키가 있는지 확인한다.
func HasKey(path, key string) bool {
	lines, err := readLines(path)
	if err != nil {
		return false
	}
	for _, line := range lines {
		if k, _, ok := parseLine(line); ok && k == key {
			return true
		}
	}
	return false
}

// parseLine은 주석·빈 줄을 걸러내고 KEY=VALUE를 분리한다.
func parseLine(line string) (key, value string, ok bool) {
	stripped := strings.TrimSpace(line)
	if stripped == "" || strings.HasPrefix(stripped, "#") {
		return "", "", false
	}
	k, v, found := strings.Cut(stripped, "=")
	if !found {
		return "", "", false
	}
	return strings.TrimSpace(k), strings.TrimSpace(v), true
}

func readLines(path string) ([]string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return strings.Split(strings.TrimSuffix(string(raw), "\n"), "\n"), nil
}

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0o644)
}

// Dir은 경로의 디렉터리 부분을 반환한다(없으면 ".").
func Dir(path string) string {
	return filepath.Dir(path)
}
