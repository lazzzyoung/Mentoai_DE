BINARY := bin/mentoai

.PHONY: build run test lint fmt check tidy check-secrets hooks migrate seed pipeline up down logs logs-caddy deploy ubuntu-setup ubuntu-setup-go release deploy-native

build:
	go build -trimpath -ldflags "-s -w" -o $(BINARY) ./cmd/mentoai

run: build
	$(BINARY) serve

test:
	go test -race -shuffle=on ./...

lint:
	go vet ./...

fmt:
	gofmt -w cmd internal

check: check-secrets lint test

tidy:
	go mod tidy

clean:
	rm -rf bin data

# --- 파이프라인 편의 명령 ---

migrate: build
	$(BINARY) migrate

seed: build
	$(BINARY) seed

pipeline: build
	$(BINARY) pipeline

# --- Docker / 배포 ---

# 원터치 배포: 의존성 확인/설치 → .env 준비 → 빌드·기동 → 헬스체크 (우분투 기준 검증)
deploy:
	bash scripts/deploy.sh

# 우분투 최초 설정: Docker Engine + Compose 설치 (sudo 필요)
ubuntu-setup:
	sudo bash scripts/setup-ubuntu.sh

# + 로컬 테스트/CLI용 Go 툴체인까지 설치
ubuntu-setup-go:
	sudo bash scripts/setup-ubuntu.sh --with-go

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

logs-caddy:
	docker compose logs -f caddy

# --- 네이티브(무도커) 배포: 로컬 크로스컴파일 → rsync → systemd ---

# linux 크로스컴파일: ARCH=amd64|arm64 (기본 amd64)
release:
	ARCH=$${ARCH:-amd64}; \
	CGO_ENABLED=0 GOOS=linux GOARCH=$$ARCH go build -trimpath -ldflags "-s -w" -o dist/mentoai-linux-$$ARCH ./cmd/mentoai

# 사용법: make deploy-native HOST=root@서버IP [ARCH=amd64|arm64] [PORT=22]
deploy-native:
	@test -n "$(HOST)" || { echo "사용법: make deploy-native HOST=user@host [ARCH=amd64|arm64] [PORT=22]"; exit 1; }
	test -n "$$ARCH" || ARCH=amd64; test -n "$$PORT" || PORT=22
	bash scripts/deploy-native.sh "$(HOST)" "$$ARCH" "$$PORT"

# --- 보안 ---

# 시크릿 유출 1차 검사 (배포 스크립트·CI·pre-commit이 호출)
check-secrets:
	bash scripts/check-secrets.sh

# pre-commit 훅 설치 (커밋마다 시크릿 검사)
hooks:
	install -m 0755 scripts/hooks/pre-commit .git/hooks/pre-commit
