#!/usr/bin/env bash
# 시크릿 유출 1차 게이트: 배포·커밋 전에 코드 레벨로 검사한다.
#
# 원칙: 시크릿은 **로컬 .env와 배포 서버의 .env에만** 존재한다.
#   검사 1) .env 계열 파일이 git에 추적되면 즉시 실패
#   검사 2) git 추적 파일 전체를 위험 패턴(Google/AWS/Sentry/OpenAI/Slack/Telegram/
#           프라이빗 키, 길이 긴 SECRET/TOKEN 대입)으로 스캔
#   검사 3) 로컬 .env의 실제 시크릿 "값"이 코드·빌드 산출물(바이너리)에
#           하드코딩/새어들었는지 값 기반 검사
#
# 사용법: bash scripts/check-secrets.sh   (배포 스크립트와 CI, pre-commit이 호출)
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

FAILED=0
fail() { printf '\033[1;31m[시크릿 검사] 유출 징후:\033[0m %s\n' "$*"; FAILED=1; }
info() { printf '\033[1;36m[시크릿 검사]\033[0m %s\n' "$*"; }

# --- 검사 1) .env 계열 추적 여부 (.env.example 템플릿은 추적 허용) ---
tracked_env=$(git ls-files -- '.env' '.env.*' '*.env' '*/*.env' '*/*.env.*' 2>/dev/null | grep -v '^\.env\.example$')
if [[ -n $tracked_env ]]; then
  fail "다음 .env 계열 파일이 git에 추적된다: $tracked_env (git rm --cached 로 제거 필요)"
else
  info ".env 계열 미추적 확인 (.env.example 템플릿 제외)"
fi

# --- 검사 2) 추적 파일 패턴 스캔 (.env.example도 대상 — 실제 값이면 적발된다) ---
PATTERNS=(
  'AIza[0-9A-Za-z_-]{30,}'                                # Google API 키
  'AKIA[0-9A-Z]{16}'                                      # AWS 액세스 키
  'https://[0-9a-f]{10,}@[a-z0-9.-]+sentry\.(io|us)'      # Sentry DSN
  'sk-[A-Za-z0-9_-]{20,}'                                 # OpenAI 스타일 키
  'gh[pousr]_[A-Za-z0-9]{36}'                             # GitHub 토큰
  'xox[baprs]-[0-9A-Za-z-]{10,}'                          # Slack 토큰
  '[0-9]{8,10}:AA[A-Za-z0-9_-]{33}'                       # Telegram 봇 토큰
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'                    # 프라이빗 키 블록
)
for pat in "${PATTERNS[@]}"; do
  if git grep -nIE -- "$pat" -- . >/dev/null 2>&1; then
    fail "패턴 유출 정황 ($(git grep -nIE -- "$pat" -- . | head -3 | tr '\n' ' '))"
  fi
done
info "추적 파일 패턴 스캔 완료 (${#PATTERNS[@]}종)"

# --- 검사 3) 로컬 .env 실제 값이 코드·산출물에 새었는지 ---
scan_file_for_values() {
  local file=$1 values_hit=0 key value
  [[ -f $file ]] || return 0
  while IFS='=' read -r key value; do
    value=${value%\"}; value=${value#\"}; value=${value%\'}; value=${value#\'}
    [[ -n $value && ${#value} -ge 20 ]] || continue
    case $key in
      *SECRET*|*TOKEN*|*PASSWORD*|*API_KEY*|*DSN*) ;;
      *) continue ;;
    esac
    # git 추적 파일에서 값 검색
    if git grep -qF -- "$value" -- . 2>/dev/null; then
      fail "[$key] 값이 git 추적 파일에 존재: $(git grep -lF -- "$value" -- . | head -2 | tr '\n' ' ')"
      values_hit=1
    fi
    # 빌드 산출물(바이너리)에서 값 검색 — 시크릿은 런타임 env에서만 와야 한다
    for artifact in bin/* dist/*; do
      if [[ -f $artifact ]] && grep -qaF -- "$value" "$artifact" 2>/dev/null; then
        fail "[$key] 값이 빌드 산출물에 포함됨: $artifact"
        values_hit=1
      fi
    done
  done < "$file"
  return $values_hit
}

if [[ -f .env ]]; then
  if scan_file_for_values .env; then
    info ".env 실제 값 미새출 확인 (코드·바이너리)"
  fi
else
  info ".env 없음 — 값 검사 생략"
fi

# --- 결과 ---
if [[ $FAILED -eq 1 ]]; then
  printf '\033[1;31m[시크릿 검사] 실패 — 배포/커밋을 중단합니다.\033[0m\n' >&2
  exit 1
fi
printf '\033[1;32m[시크릿 검사] 통과\033[0m\n'
exit 0
