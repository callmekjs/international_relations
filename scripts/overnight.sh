#!/usr/bin/env bash
# 밤새 혼자 끝까지 가는 순서.
#
#   1. 글자 있는 연도를 띄어쓰기 고침으로 다시 뽑는다
#   2. 스캔본 OCR 이 끝날 때까지 기다린다 (다른 창에서 이미 돌고 있다)
#   3. 기준선을 새로 깔고 → 연도별 점검 → 정권별 묶기 → 최종 점검
#
# 로그는 logs/overnight/ 에 남는다. 아침에 report.txt 만 보면 된다.
set -u
cd "$(dirname "$0")/.."
LOG=logs/overnight
mkdir -p "$LOG"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG/report.txt"; }

TEXT_YEARS="1997 1998 1999 2000 2001 2002 2003 2004 2006 2007 2008 2009 2010 2011 2012 2014 2015 2016 2018 2020 2021 2022 2023 2024 2025"

say "=== 1. 글자 있는 연도 다시 뽑기 (띄어쓰기 되살리기 적용) ==="
ARGS=""
for y in $TEXT_YEARS; do ARGS="$ARGS --year $y"; done
python scripts/etl.py $ARGS --force > "$LOG/1-etl.log" 2>&1
say "    끝. 실패한 파일: $(grep -c '실패' "$LOG/1-etl.log" || echo 0)건"

say "=== 2. 스캔본 OCR 기다리는 중 (1989~1996) ==="
WAITED=0
while [ ! -f etl_test/1996/meta.json ]; do
  sleep 120; WAITED=$((WAITED+2))
  if [ $((WAITED % 30)) -eq 0 ]; then
    say "    ${WAITED}분 경과 — 끝난 연도: $(ls etl_test | grep -cE '^19(89|9[0-6])$')/8"
  fi
  if [ $WAITED -gt 480 ]; then say "    8시간 넘음 — 기다리기 그만둔다"; break; fi
done
say "    OCR 완료 연도: $(ls etl_test | grep -cE '^19(89|9[0-6])$')/8"

say "=== 3. 기준선 새로 깔기 ==="
python scripts/check.py --all --save-baseline > "$LOG/2-baseline.log" 2>&1
say "    저장 $(grep -c '기준선' "$LOG/2-baseline.log" || echo 0)건"

say "=== 4. 연도별 점검 ==="
python scripts/check.py --all > "$LOG/3-check.log" 2>&1
say "    오류 $(grep -c '^  오류' "$LOG/3-check.log" || echo 0)건 · 미완 $(grep -c '^  미완' "$LOG/3-check.log" || echo 0)건"
grep -B0 '^  오류' "$LOG/3-check.log" | head -20 >> "$LOG/report.txt" 2>/dev/null

say "=== 5. 정권별 묶기 ==="
python scripts/corpus.py > "$LOG/4-corpus.log" 2>&1
say "    $(tail -3 "$LOG/4-corpus.log" | tr '\n' ' ')"

say "=== 6. 최종 점검 ==="
python scripts/final_check.py > "$LOG/5-final.log" 2>&1
say "    $(tail -3 "$LOG/5-final.log" | tr '\n' ' ')"

say "=== 다 끝났다 ==="
