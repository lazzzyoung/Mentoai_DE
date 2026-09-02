# syntax=docker/dockerfile:1
# CGO 없이 정적 빌드 → 실행 이미지는 distroless의 단일 바이너리.

FROM golang:1.27-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags "-s -w" -o /out/mentoai ./cmd/mentoai

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/mentoai /mentoai
ENV SQLITE_PATH=/data/mentoai.db
VOLUME ["/data"]
EXPOSE 8000
# serve는 시작 시 마이그레이션을 자동 적용한다 (tzdata는 바이너리에 포함).
ENTRYPOINT ["/mentoai"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
