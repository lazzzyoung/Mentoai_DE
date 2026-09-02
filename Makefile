BINARY := bin/mentoai

.PHONY: build run test lint fmt check tidy clean migrate seed pipeline up down logs

build:
	go build -ldflags "-s -w" -o $(BINARY) ./cmd/mentoai

run: build
	$(BINARY) serve

test:
	go test ./...

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

# --- Docker ---

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api
