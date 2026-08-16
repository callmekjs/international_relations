#!/usr/bin/env bash
# 스캔본 OCR 이 끝나면 나머지를 자동으로 이어서 돌린다.
#
#   1. 스캔본 OCR (1989~1996) — 이 스크립트가 직접 돌린다
#   2. 기준선 새로 깔기 → 연도별 점검 → 정권별 묶기 → 최종 점검
#
# 로그는 logs/overnight/ 에 남는다. 아침에 report.txt 만 보면 된다.
#
# 2026-08-16 교훈: OCR 을 다른 창에서 돌리고 이 스크립트가 '기다리기'만 하면,
# 그쪽이 죽어도 여기는 모른다. 실제로 빈 폴더 하나 때문에 OCR 이 01:30 에
# 멈췄는데 이 스크립트는 07:00 까지 태평하게 기다렸다. **직접 돌린다.**
set -u
cd "$(dirname "$0")/.."
LOG=logs/overnight
mkdir -p "$LOG"
say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG/report.txt"; }

SCAN_YEARS="1990 1991 1992 1993 1994 1995 1996"

# 그 해에 못 읽은 파일이 몇 개인지. 0 이면 온전히 끝난 것이다.
failed_of() {
  python -c "
import json,sys
try:
    m=json.load(open('etl_test/$1/meta.json',encoding='utf-8'))
    print(m['files']['failed'])
except Exception:
    print(-1)      # meta.json 자체가 없다 = 아예 안 했다
" 2>/dev/null
}

say "=== 1. 스캔본 OCR (한자 인식 켬) ==="
# 두 바퀴 돈다. 첫 바퀴에서 못 읽은 파일이 남으면 한 번 더 시도한다 —
# 2026-08-16 에 프로세스를 중간에 죽였더니 그때 돌던 tesseract 가 전부
# '실패'로 기록됐다. 진짜 못 읽는 파일과 사고로 끊긴 파일은 다시 해보면 갈린다.
for PASS in 1 2; do
  for y in $SCAN_YEARS; do
    F=$(failed_of "$y")
    if [ "$F" = "0" ]; then
      [ "$PASS" = "1" ] && say "    $y 이미 끝남 — 건너뜀"
      continue
    fi
    if [ "$PASS" = "2" ]; then say "    $y 다시 시도 (지난번 못 읽은 파일 ${F}개)"
    else say "    $y 시작"; fi
    python scripts/etl.py --year "$y" --force >> "$LOG/1-ocr.log" 2>&1
    F=$(failed_of "$y")
    if [ "$F" = "0" ]; then
      say "    $y 끝  $(python -c "
import json;m=json.load(open('etl_test/$y/meta.json',encoding='utf-8'))
print(f\"{m['counts']['pages']}쪽 {m['counts']['sentences']}문장\")" 2>/dev/null)"
    else
      say "    $y 못 읽은 파일 ${F}개 남음"
    fi
  done
done

say "=== 2. 기준선 새로 깔기 ==="
python scripts/check.py --all --save-baseline > "$LOG/2-baseline.log" 2>&1
say "    끝"

say "=== 3. 연도별 점검 ==="
python scripts/check.py --all > "$LOG/3-check.log" 2>&1
say "    오류 $(grep -c '^  오류' "$LOG/3-check.log") 건 · 미완 $(grep -c '^  미완' "$LOG/3-check.log") 건"
awk '/^  [0-9]{4}년 —/{y=$1} /^  오류/{print "        " y " " $0}' "$LOG/3-check.log" | tee -a "$LOG/report.txt"

say "=== 4. 정권별 묶기 ==="
python scripts/corpus.py > "$LOG/4-corpus.log" 2>&1
say "    $(tail -2 "$LOG/4-corpus.log" | tr '\n' ' ')"

say "=== 5. 최종 점검 ==="
python scripts/final_check.py > "$LOG/5-final.log" 2>&1
say "    $(tail -2 "$LOG/5-final.log" | tr '\n' ' ')"

say "=== 다 끝났다 ==="
