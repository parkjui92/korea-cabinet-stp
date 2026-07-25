#!/usr/bin/env bash
# Supabase 재적재 — 주간 갱신 후 실행.
#
# 흐름: 파싱 결과 → REST JSON 변환 → truncate → 대량 POST → 검증.
# anon 키는 적재 중 임시로 쓰기가 열려야 하는데, lockdown 마이그레이션이
# 쓰기를 막아둔 상태다. 그래서 재적재는 **execute_sql(수퍼유저)로 truncate**한
# 뒤, 이 스크립트가 아니라 아래 안내대로 진행한다.
#
# ── 재적재 절차 ──
# 1) REST JSON 재생성:
#      uv run --with pyyaml python run_emit_rest_json.py
# 2) Supabase에서 기존 데이터 비우기 (Claude/SQL 편집기):
#      truncate agenda_item, utterance, report_item, meeting, ministry cascade;
#      -- RLS·정책·뷰는 유지된다(truncate는 데이터만 지움)
# 3) 적재 중에만 쓰기 임시 허용:
#      grant insert on ministry, meeting, agenda_item, utterance, report_item to anon;
# 4) 이 스크립트 실행:  ./load_supabase.sh <ANON_KEY>
# 5) 쓰기 회수(다시 읽기 전용):
#      revoke insert on ministry, meeting, agenda_item, utterance, report_item from anon;
#
# 초기 적재는 RLS 켜기 전이라 이 단계들이 필요 없었다. 갱신부터 위 절차를 쓴다.

set -euo pipefail
ANON="${1:?사용법: ./load_supabase.sh <ANON_KEY>}"
BASE="https://jowsfgrekxfvfoniwvpj.supabase.co/rest/v1"
DIR="$(dirname "$0")/data/rest"

post() {
  local table=$1 file=$2
  local code
  code=$(curl -s -X POST "$BASE/$table" \
    -H "apikey: $ANON" -H "Authorization: Bearer $ANON" \
    -H "Content-Type: application/json" -H "Prefer: return=minimal" \
    --data-binary @"$file" -w "%{http_code}" -o /tmp/rest_err.txt)
  printf "  %s  %s\n" "$code" "$(basename "$file")"
  if [ "$code" != "201" ]; then head -c 400 /tmp/rest_err.txt; echo; exit 1; fi
}

# FK 순서: 부처·회의 먼저, 그다음 참조 테이블.
for f in "$DIR"/ministry.*.json;    do post ministry    "$f"; done
for f in "$DIR"/meeting.*.json;     do post meeting     "$f"; done
for f in "$DIR"/agenda_item.*.json; do post agenda_item "$f"; done
for f in "$DIR"/utterance.*.json;   do post utterance   "$f"; done
for f in "$DIR"/report_item.*.json; do post report_item "$f"; done

echo "적재 완료. execute_sql로 행 수 검증 권장."
