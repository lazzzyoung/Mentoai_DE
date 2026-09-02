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

# 원터치 배포: api(마이그레이션+시드 자동) + caddy(HTTPS·HTTP/3 자동)가 함께 뜬다.
# 실제 도메인으로 배포하려면 .env에 CADDY_DOMAIN=도메인 을 넣고 80/443(tcp+udp)을 연다.
up:
	docker compose up -d --build

deploy: up

down:
	docker compose down

logs:
	docker compose logs -f api

logs-caddy:
	docker compose logs -f caddy
