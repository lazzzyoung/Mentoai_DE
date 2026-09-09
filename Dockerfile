# syntax=docker/dockerfile:1
# CGO 없이 정적 빌드 → 실행 이미지는 distroless의 단일 바이너리.
# BuildKit 캐시 마운트로 모듈/빌드 캐시를 재사용해 재배포 빌드가 수 초로 끝난다.

FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go mod download
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags "-s -w" -o /out/mentoai ./cmd/mentoai \
    && mkdir -p /out/data

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/mentoai /mentoai
# nonroot(65532) 소유의 /data를 이미지에 심는다 — 새 볼륨 마운트 시 소유권이 복사되어
# distroless nonroot 유저로도 SQLite 파일을 쓸 수 있다.
COPY --from=build --chown=65532:65532 /out/data /data
ENV SQLITE_PATH=/data/mentoai.db
# GC 소프트 리밋: 컨테이너 메모리 오버플로 전에 GC가 먼저 반응하게 한다.
# 현재 실사용 ~30MB 기준 넉넉한 상한이다.
ENV GOMEMLIMIT=64MiB
VOLUME ["/data"]
EXPOSE 8000
# serve는 시작 시 마이그레이션을 자동 적용한다 (tzdata는 바이너리에 포함).
ENTRYPOINT ["/mentoai"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
