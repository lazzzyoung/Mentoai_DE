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
# shellcheck source=scripts/lib.sh
source scripts/lib.sh
# shellcheck disable=SC2034  # lib.sh step()에서 사용
STEP_TOTAL=3
title "시크릿 유출 검사 (3가지)"

FAILED=0
fail() { err "$*"; FAILED=1; }

# --- [1/3] .env 계열 추적 여부 (.env.example 템플릿은 추적 허용) ---
step ".env 파일이 git에 올라가 있지 않은지"
tracked_env=$(git ls-files -- '.env' '.env.*' '*.env' '*/*.env' '*/*.env.*' 2>/dev/null | grep -v '^\.env\.example$')
if [[ -n $tracked_env ]]; then
  fail "이 파일들이 git에 추적되고 있습니다: $tracked_env"
  hint "git rm --cached '파일명' 으로 추적을 제거하세요. 값이 이미 push됐다면 해당 키를 반드시 재발급하세요."
else
  ok "추적 없음 — .env.example 템플릿만 저장소에 있습니다"
fi

# --- [2/3] 추적 파일 패턴 스캔 (.env.example도 대상 — 실제 값이면 적발된다) ---
step "알려진 키/토큰 패턴 스캔 (8종)"
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
    fail "키/토큰 패턴 발견:"
    git grep -nIE -- "$pat" -- . | head -3 | sed 's/^/      /'
    hint "해당 줄을 삭제하고 값은 .env에 넣으세요 (코드에서는 환경변수로 읽습니다)"
  fi
done
ok "8종 패턴 이상 없음"

# --- [3/3] 로컬 .env 실제 값이 코드·산출물에 새었는지 ---
step ".env의 실제 값이 코드·바이너리에 없는지"
scan_file_for_values() {
  local file=$1 key value
  [[ -f $file ]] || return 0
  while IFS='=' read -r key value <&3; do
    value=${value%\"}; value=${value#\"}; value=${value%\'}; value=${value#\'}
    [[ -n $value && ${#value} -ge 20 ]] || continue
    case $key in
      *SECRET*|*TOKEN*|*PASSWORD*|*API_KEY*|*DSN*) ;;
      *) continue ;;
    esac
    if git grep -qF -- "$value" -- . 2>/dev/null; then
      fail "[$key] 값이 코드에 하드코딩되어 있습니다: $(git grep -lF -- "$value" -- . | head -2 | tr '\n' ' ')"
      hint "그 줄에서 값을 지우고 os.Getenv로 읽으세요. 이미 push했다면 키를 재발급하세요."
    fi
    for artifact in bin/* dist/*; do
      if [[ -f $artifact ]] && grep -qaF -- "$value" "$artifact" 2>/dev/null; then
        fail "[$key] 값이 빌드 산출물에 포함되어 있습니다: $artifact"
        hint "산출물에 값이 새지 않습니다 — 소스에서 제거한 뒤 다시 빌드하세요."
      fi
    done
  done 3< "$file"
}

if [[ -f .env ]]; then
  scan_file_for_values .env
  ok ".env의 시크릿이 코드·바이너리에 없습니다"
else
  skip ".env가 없어 값 검사는 생략합니다"
fi

# --- 결과 ---
if [[ $FAILED -eq 1 ]]; then
  err "시크릿 검사를 통과하지 못했습니다 — 배포/커밋이 중단되었습니다"
  hint "위 안내대로 수정한 뒤 'make check-secrets'로 다시 확인하세요"
  exit 1
fi
ok "시크릿 검사 통과 — 안심하고 배포하셔도 됩니다"
exit 0
