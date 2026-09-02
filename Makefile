BINARY := bin/mentoai

.PHONY: build run test lint fmt check tidy clean migrate seed pipeline up down logs

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

check: lint test

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
