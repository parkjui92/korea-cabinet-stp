# 과학기술정책 국무회의 아카이브

**국무회의에서 무엇이 의결되었는가**를 과학기술정책 축으로 열람·분석하는 아카이브.

🔗 **[korea-cabinet-stp.parkjui92.workers.dev](https://korea-cabinet-stp.parkjui92.workers.dev)**

2018년 9월부터 2026년 7월까지 국무회의 **447회 · 안건 16,742건**을 공식
「의사일정」 원문에서 전수 추출하고, 과기정통부·산업부·데이터처 등 과학기술
정책 축으로 분류했다. 대통령·국무위원 발언 4,603건을 회차로 이어 붙여
**"어떤 발언이 어떤 의결로 이어졌는지"** 까지 추적한다.

---

## 왜 만들었나

국무회의가 무엇을 의결하는지는 공개돼 있지만, **연구에 쓸 형태로는 열려 있지
않다.** 세 가지 벽이 있었다.

1. **전수가 안 보인다.** [정책브리핑](https://www.korea.kr/briefing/stateCouncilList.do)
   본문은 의결 27건 중 6건만 소개한다. 안건 전수는 첨부된 `.hwp` 의사일정
   문서 안에 표로만 들어 있어, 사람이 회차마다 열어 세지 않는 한 집계가 안 된다.
   → **전수를 못 보면 "과기정책이 몇 %"라는 분모 자체를 만들 수 없다.**

2. **점유율이 왜곡된다.** 제출기관을 그대로 세면 법제처가 1위(6,110건)가 된다.
   그런데 대부분이 **법률공포안** — 국회 통과 법률을 공포하는 형식 절차이지
   정책 발의가 아니다. 이걸 걷어내지 않으면 부처 간 의제 점유가 엉킨다.

3. **시계열이 조용히 끊긴다.** 부처는 개편으로 이름이 바뀐다. 특히 산업통상
   자원부 → 산업통상부는 개명처럼 보이지만 **에너지 기능이 기후에너지환경부로
   넘어갔다**(2025-10-01). 모르고 추이를 그리면 그날의 급락을 정책 변화로 오독한다.

이 아카이브는 세 벽을 넘도록 만들었다 — 안건 **전수 추출**, 형식 안건을 분리한
**정직한 분모**, 개편을 흡수한 **부처 정규화**.

---

## 무엇을 볼 수 있나

**공개 대시보드** — [korea-cabinet-stp.parkjui92.workers.dev](https://korea-cabinet-stp.parkjui92.workers.dev)

| 기능 | 설명 |
|---|---|
| **안건 열람·필터** | 전체 16,742건. 과기정책 필터 기본 ON(1,008건). 부처·주제·기간·정책안건 여부로 좁힘 |
| **교차 검색** | 안건 제목 + 발언 전문 동시 검색. 발언에서 맞으면 → **그 회의 의결 안건**으로 바로 이동 |
| **판정 근거** | 각 안건이 왜 과기정책으로 잡혔는지(`소관 과학기술정보통신부 · 주제어 '인공지능'`) 표시 |
| **원문 링크** | 안건마다 korea.kr 원문으로 역참조 (공공누리 출처표시) |
| **CSV 내려받기** | 화면에 필터 건 그대로 export. R·엑셀 바로 사용(UTF-8 BOM) |

**한눈에 드러난 것 — 정권별 과기정책 비중이 단조 증가한다:**

| 정권 | 정책안건 | 과기정책 관련 | 비중 |
|---|---:|---:|---:|
| 문재인 (2018-09~2022-05) | 4,521 | 254 | 5.6% |
| 윤석열 (2022-05~2025-05) | 3,765 | 276 | 7.3% |
| 이재명 (2025-06~2026-07) | 1,131 | 103 | **9.1%** |

---

## 어떻게 쓰나

### 1) 그냥 열람 — 브라우저

[대시보드](https://korea-cabinet-stp.parkjui92.workers.dev)에서 검색·필터.
예: 검색창에 `GPU` → 대통령의 "고성능 GPU 1만장 확보" 발언 → 클릭하면 그날 의결된
안건 전체.

### 2) 계량분석 — SQL / R / Python

전체 데이터가 Supabase Postgres에 정규화 적재돼 있다(읽기 전용 공개). 분석용 뷰
`v_policy_agenda`(정책안건만 = 점유율 표준 분모), `v_agenda`(정권·부처 파생),
`v_meeting_summary`(회의별 요약).

```sql
-- 정권별 과기정책 비중
select era, count(*) as items,
       count(*) filter (where is_stc) as stc,
       round(100.0*count(*) filter (where is_stc)/count(*), 1) as pct
from v_policy_agenda group by era;
```

R은 `RPostgres`, Python은 `psycopg2`로 접속한다. 발언 전문(`utterance.body`)에는
한국어 trigram 인덱스가 있어 유사도 검색도 된다.

### 3) 자연어 질의 — 각자 자기 Claude Code

공개 사이트에 AI 키를 심는 대신, 연구자가 자기 Claude Code를 이 Supabase에
붙여 자연어로 묻는다. "2025년 이후 부처별 AI 안건 세줘" → SQL로 번역·실행.

### 4) 데이터 파일 직접

`data/export/*.jsonl`에 원천 데이터가 있다. `site/data/bundle.json`은 대시보드가
쓰는 통합 번들.

---

## 데이터 구조

세 레이어를 **회차 키**로 잇는다.

```
회의(meeting) ─┬─ 안건(agenda_item)   의결된 것 · 16,742건
               ├─ 발언(utterance)     담론 · 4,603건 (화자 구분)
               └─ 보고·토의(report)   의결 안 되는 의제 · 151건
```

- **안건** = 의사일정 첨부에서 전수 추출. `role`(정책안건/법률공포/조직직제/인사),
  `is_stc`(과기 여부), `tags`, 정규화된 `ministry_id`.
- **발언** = 모두말씀 첨부. 화자가 문서에 명시돼 ASR 추정이 불필요.
  `attribution`으로 근거 등급 구분(문서 표기 / 문서 정의상 대통령).
- **보고·토의** = 의결 없이 상정된 의제. 「하반기 경제성장전략」 같은 보고는
  여기서만 잡힌다.

분류(부처·태그·역할)는 파이썬 파이프라인이 계산해 굽는다. 대시보드·DB 어디서도
재판정하지 않는다 — 기준이 흩어지면 조용히 어긋나기 때문이다.

---

## 출처와 라이선스

- **데이터** — 대한민국 정책브리핑(문화체육관광부) 국무회의 브리핑 첨부 문서를
  가공한 2차 저작물. [공공누리 제1유형(출처표시)](https://www.kogl.or.kr/info/license.do).
  상세·한계는 [`DATA_LICENSE.md`](DATA_LICENSE.md).
- **코드** — [MIT](LICENSE).
- 사진·이미지·동영상은 제3자 저작권이라 **포함하지 않았다.**

### 이 데이터로 알 수 없는 것

**의안 심의는 비공개다.** 안건별 찬반·심의 발언은 어떤 공개 출처에도 없다.
여기서 얻는 것은 *무엇이 상정·의결되었는가*이지 *어떻게 논의되었는가*가 아니다.
연구에서 "국무회의에서 논의되었다"고 쓸 때 이 선을 넘으면 안 된다.

---

## 재현·갱신

국무회의는 매주 화요일. 파이프라인은 증분식이라 재실행하면 새 회차만 처리한다.

```bash
python3 run_collect_list.py && python3 run_collect_attachments.py   # 수집
uv run --with pyyaml python run_parse_agendas.py                    # 안건
uv run --with pyyaml python run_parse_remarks.py                    # 발언
uv run --with pyyaml python run_parse_reports.py                    # 보고·토의
uv run --with pyyaml python run_build_site_data.py                  # 사이트 번들
uv run --with pyyaml python run_emit_rest_json.py                   # Supabase 적재분
uv run --with pytest --with pyyaml python -m pytest tests/ -q       # 테스트 60개
```

방법론과 개발 과정에서 잡은 데이터 함정(colSpan 병합·화자 오인·중복 선언 등)은
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)에 정리했다.
