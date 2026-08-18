# POSCO International 에너지 Backfill 조사 범위 및 커버리지

## 조사 기준

- 조사일시: 2026-08-19 (KST)
- 대상 기간: 2024-08-19 ~ 2026-08-19
- 대상: POSCO International(Senex Energy, Myanmar gas field, LNG terminal·power generation·trading)과 가격·물량·계약·CAPEX·현금흐름을 바꾸는 외부 변화
- 우선 출처: 호주 ACCC·AEMO·정부, 한국 산업통상자원부, IEA, POSCO International/Senex 공식 IR·보도자료
- 기존 knowledge 확인: `market_sensing.py search market-sensing-wiki --query "POSCO International energy Senex gas reservation LNG Myanmar gas field terminal trading" --limit 20`
- 시작 audit 기준값: 2026-08-19 `unpublished_claims=0`, `unpublished_sources=0`, `signal_schema=0`, `signal_integrity=0`, `signal_quality=0`, `pending_reviews=0`
- 저장 범위: 이 폴더의 후보 Markdown·manifest·coverage·publication-plan만 작성. `.system/`·자동생성 Markdown·등록 raw는 수정하지 않음.

## 실제 검색 쿼리

1. `POSCO International 2024 third quarter earnings LNG Senex Myanmar gas field terminal`
2. `Senex Atlas gas first gas 2024 official` / `Senex Atlas gas first gas 2025 official`
3. `AEMO Gas Statement of Opportunities 2025 east coast gas`
4. `ACCC gas inquiry September 2024 east coast supply` / `ACCC March 2025 supply demand gas`
5. `Korea 11th Basic Plan Electricity Supply Demand 2025 LNG official`
6. `IEA Gas Market Report Q3 2025 LNG supply official`
7. `POSCO International 2025 Q3 results Senex gas` / `POSCO Holdings 2025 results Senex LNG`
8. 저장지식 중복 확인: `Senex`, `gas reservation`, `AEMO`, `Myanmar gas`, `LNG terminal`, `POSCO International` 조합 검색.

## 확인·선정 URL

| 날짜 | 원문 | 확인 결과 | 선정 이유 |
|---|---|---|---|
| 2024-09-27 | ACCC Q1 2025 gas outlook | 공개 HTML 확인 | 12~27 PJ 잉여와 단기 부족 위험, Senex 계약·전송 영향 |
| 2024-10-30 | POSCO International 3Q 2024 IR PDF | PDF 14쪽 확인 | Myanmar 유지보수·Cost Recovery와 Senex 단가·터미널·발전 손익 분리 |
| 2024-11-25 | Senex Atlas expansion opening | 공개 HTML 확인 | A$1bn·60 PJ·first gas 예정·장기 고객계약·CAPEX 회수 |
| 2024-12-04 | POSCO International Atlas Unit 1 test operation | 공개 HTML 확인 | 시운전→상업판매 게이트, Units 2·3·280 wells 후속상태 |
| 2025-02-21 | 산업통상자원부 제11차 전기본 | HTML·첨부 PDF 링크 확인 | LNG 용량시장·열병합·ESS·2038 전원믹스가 발전·터미널 수요 변경 |
| 2025-02-28 | Senex Atlas first gas | 공개 HTML 확인 | 실제 시장 유입·Orora 고객 인도·프로젝트 지출 확인 |
| 2025-03-20 | AEMO 2025 GSOO PDF | PDF 114쪽 확인 | 2028 피크·2029 구조적 부족, Atlas 57 TJ/d·Roma North 28.5 TJ/d 반영 |
| 2025-03-27 | ACCC Q3 supply outlook | 공개 HTML·GSA 보고서 확인 | 9 PJ 동부·40 PJ 남부 부족, LNG 미계약 가스·가격·저장 의존 |
| 2025-06-30 | ACCC Q4 2025/2026 outlook | 공개 HTML 확인 | 가격 하락과 공급전망 악화의 간극, 2026 부족 위험 |
| 2025-07-22 | IEA Gas Market Report Q3 2025 | Executive summary 확인 | 2025 타이트한 아시아·유럽 화물경쟁과 2026 공급증가 교차 |
| 2025-10-27 | POSCO International 3Q 2025 IR PDF | PDF 에너지 4쪽 확인 | Senex 판매량·매출·영업이익 증산 실현과 Myanmar 회수율 하락 병존 |
| 2026-02-03 | POSCO Holdings FY2025 results | 공개 HTML 확인 | 2025 실적·2026 계획에서 Senex LNG 지속 추가이익 확인 |

## 접근 실패·제한 URL

| URL | 시도 | 결과·분류 | 대체 확인 |
|---|---|---|---|
| ACCC December 2024 interim report 페이지 | 웹 공개 페이지 click, timeout | 최종 페이지 timeout (`network`/`content_missing` 혼합) | ACCC 직접 PDF `https://www.accc.gov.au/system/files/accc-gas-inquiry-interim-report-december-2024.pdf` 및 2025-03-27 ACCC 후속자료 확인 |
| Senex 2024 sustainability report | 공개 페이지 open | 도구 내부 오류로 본문 직접 추출 불가 | Senex 2024-11-25 opening과 2025-02-28 first gas 공식 HTML로 동일 프로젝트 후속 확인 |
| ACCC March GSA PDF 직접 다운로드 | HTML 페이지를 먼저 확인 | HTML 본문·PDF 링크는 확인, PDF 본문은 ACCC media release로 교차 | 2025-03-27 ACCC supply outlook HTML에서 가격·계약수치 확인 |

검색 스니펫만으로 Claim을 확정하지 않았으며, 각 선정 후보는 원문 HTML/PDF의 핵심 문장과 날짜를 직접 확인했습니다.

## 선정·제외 이유

- 선정: Senex 증산의 자금·시설·first gas·실제 손익 후속상태를 연결하고, ACCC/AEMO의 동부가스 가격·수급·운송 조건과 한국 LNG 수요정책·IEA 글로벌 LNG 변동을 연결할 수 있는 12건.
- 동일 프로젝트 관계: 2024-11-25 개장과 2024-12-04 Unit 1 시운전은 같은 Atlas expansion이지만 상태·시점이 달라 별도 후보로 보존하고 manifest의 중복 후보에 상호 연결.
- 제외: 2024-08-19 이전 POSCO Q2 2024, 2024-07-29 Gwangyang Terminal 1 준공, 2024-06 Senex 자본증자, 2026-05 호주 가스예약제·2026-03 AEMO GSOO·2026-07 POSCO Holdings Q2는 저장지식에 이미 등록된 후보 또는 범위 밖/중복으로 제외.
- 제외: 단순 국제 가스가격·재생에너지 추세, 회사 영향 경로·가격·물량·계약·CAPEX가 확인되지 않는 기사, 같은 보도자료를 재인용한 2차 기사.

## 후속 상태

2024년 Atlas 투자·개장 → 2024년 Unit 1 시운전 → 2025년 2월 first gas → 2025년 3분기 신규시설 증산·손익 반영 → 2026년 그룹 성장계획으로 연결했습니다. 2025년 ACCC/AEMO의 단기 부족·2028~29년 구조적 공백은 Senex 증산이 “해결 완료”가 아니라 계약·저장·전송 투자의 조건부 완충임을 확인하는 독립 후속 근거입니다.

