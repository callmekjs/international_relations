#!/usr/bin/env bash
# 밤샘 작업이 멈추면 **혼자 다시 일으켜 세운다.**
#
# 2026-08-16 새벽, 빈 폴더 하나 때문에 OCR 이 01:30 에 멈췄는데 아무도
# 몰랐다. 아침에 보니 5시간 반이 통째로 날아가 있었다. 사람이 자는 동안
# 지켜볼 수 없으니 **기계가 지켜보게 한다.**
#
# 5분마다 확인해서
#   - overnight.sh 가 살아 있으면        → 그대로 둔다
#   - 죽었는데 아직 안 끝났으면          → 다시 띄운다
#   - '다 끝났다' 가 로그에 있으면       → 감시를 마친다
#
# overnight.sh 는 이미 끝난 연도를 건너뛰므로 몇 번을 다시 띄워도 안전하다.
set -u
cd "$(dirname "$0")/.."
LOG=logs/overnight
mkdir -p "$LOG"
WATCH="$LOG/watchdog.txt"
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$WATCH"; }

say "감시 시작"
RESTARTS=0
while true; do
  sleep 300

  if grep -q "다 끝났다" "$LOG/report.txt" 2>/dev/null; then
    say "작업 완료 확인 — 감시를 마친다 (되살린 횟수 $RESTARTS)"
    break
  fi

  if ps -ef 2>/dev/null | grep -q "[o]vernight.sh"; then
    continue                       # 살아 있다. 조용히 지나간다
  fi

  RESTARTS=$((RESTARTS + 1))
  if [ $RESTARTS -gt 20 ]; then
    say "20번 되살렸는데도 계속 죽는다 — 사람이 봐야 한다"
    break
  fi
  say "멈춰 있다 → 다시 띄운다 (${RESTARTS}번째)"
  nohup bash scripts/overnight.sh >> "$LOG/boot.log" 2>&1 &
done
