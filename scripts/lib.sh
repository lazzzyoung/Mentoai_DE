# shellcheck shell=bash
# scripts/lib.sh — 배포·검사 스크립트 공용 출력 헬퍼 (차근차근 친절 모드)
# 사용법: source "$(dirname "$0")/lib.sh" 후 STEP_TOTAL을 정의하고 step "..." 호출.
# 실패 시에는 err "무엇이" + hint "이렇게 해결하세요"를 짝지어 쓴다.

STEP_NO=${STEP_NO:-0}
STEP_TOTAL=${STEP_TOTAL:-?}

# 진행 단계 제목: step "시크릿 검사"
step() {
  STEP_NO=$((STEP_NO + 1))
  printf '\n\033[1;36m[%d/%s]\033[0m \033[1m%s\033[0m\n' "$STEP_NO" "$STEP_TOTAL" "$*"
}

# 단계 성공 표시
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }

# 건너뜀(문제 아님) 표시
skip() { printf '  \033[2m– %s (건너뜀)\033[0m\n' "$*"; }

# 주의(계속 진행) 표시
warn() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }

# 단계 실패: err "무엇이 문제" 다음에 hint "어떻게 해결"을 붙여 쓴다
err()  { printf '  \033[1;31m✗ %s\033[0m\n' "$*"; }
hint() { printf '  \033[2m→ 해결:\033[0m %s\n' "$*"; }

# 스크립트 첫머리 제목
title() { printf '\n\033[1;35m── MentoAI: %s ──\033[0m\n' "$*"; }

# 마지막 안내 목록: next "첫 번째" "두 번째" ...
next() {
  printf '\n\033[1m다음에 할 일\033[0m\n'
  while (($#)); do
    printf '  • %s\n' "$1"
    shift
  done
}
