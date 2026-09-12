// Package web은 모놀리식 UI 정적 파일을 바이너리에 임베드한다.
// 빌드 도구 없는 바닐라 JS PWA를 그대로 서빙한다.
package web

import (
	"embed"
	"io/fs"
)

//go:embed all:static
var embedded embed.FS

// FS는 static/ 하위를 루트로 하는 파일시스템이다.
func FS() fs.FS {
	sub, err := fs.Sub(embedded, "static")
	if err != nil {
		panic(err) // 임베드 경로 오류는 빌드 시점 문제다
	}
	return sub
}
