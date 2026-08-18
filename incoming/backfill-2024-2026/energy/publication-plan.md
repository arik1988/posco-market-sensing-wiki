# 에너지 Backfill publication plan

## 저장·발행 경계

이 번들의 12개 후보는 조사·수집용 incoming 원문 보존 Markdown입니다. 사용자의 지시대로 현재 작업에서는 `.system/raw/`, source-records, claims, signals, 자동 생성 MkDocs Markdown을 수정하지 않았습니다. 따라서 manifest의 `impact_estimate_draft`는 publication 단계에서 `add-source → add-claim → add-signal → set-impact-estimate`로 Source ID를 연결하기 전의 초안입니다.

## 후보별 발행 우선순위

| 우선 | 후보 | 발행 시 연결할 판단 |
|---|---|---|
| 1 | 2025-03-27 ACCC Q3 shortfall | 2025 겨울 부족·미계약 LNG·Senex 인도·저장 대응 |
| 2 | 2025-03-20 AEMO GSOO | 2028 피크·2029 구조적 공백과 Senex 장기 투자 |
| 3 | 2025-06-30 ACCC outlook | 가격 하락과 공급 악화의 간극, 2026 계약기간 |
| 4 | 2025-02-28 Senex first gas | 프로젝트 실행상태와 고객 인도·현금회수 |
| 5 | 2025-10-27 POSCO Q3 | 증산 실제 손익과 Myanmar 회수율 상쇄 |
| 6 | 2026-02-03 POSCO FY2025 | 2025 결과와 2026 자본배분 후속 상태 |
| 7 | 2024-10-30 POSCO Q3 | Myanmar·Senex·터미널·발전 자산별 기준선 |
| 8 | 2024-12-04 Unit 1 | 시운전·시설 게이트와 first gas 전제 |
| 9 | 2024-11-25 Senex opening | A$1bn·60 PJ 증산 투자·고객계약 기준선 |
| 10 | 2024-09-27 ACCC Q1 outlook | 2025 Q1 수급·남부 전송 기준선 |
| 11 | 2025-02-21 11th plan | LNG 발전·용량시장·터미널 수요 구조 |
| 12 | 2025-07-22 IEA Q3 | 글로벌 LNG 공급·가격·선복·트레이딩 선택권 |

## publication 단계 검증 체크

1. 각 후보 원문을 `add-source`로 등록하고 동일 사건의 회사 발표·정부/규제·독립자료를 supporting source 또는 독립 Source로 구분합니다.
2. 원문 수치·날짜를 원자 Claim으로 만들고 `published_at`, `event_date`, `effective_date`, `collected_at=2026-08-19`를 분리합니다.
3. 2024-11-25 개장과 2024-12-04 Unit 1은 같은 Atlas project의 서로 다른 상태로 event 연결하되 자동 병합하지 않습니다.
4. ACCC/AEMO 전망은 “출처의 전망”으로, Senex·POSCO 발표는 “회사의 발표”로 표시하고 실제 이행은 2025-02-28 first gas·2025-10-27 IR로 별도 검증합니다.
5. impact-estimate 초안의 변수는 publication 단계에서 실제 Source ID를 연결하고, 공개되지 않은 가격·원가·계약값은 `assumption`으로 유지합니다. 동일한 가스 가격·물량 충격은 여러 Signal에서 중복 합산하지 않습니다.
6. 발행 후 `sync-obsidian`, audit(특히 `unpublished_claims`, `signal_schema`, `signal_integrity`, `signal_quality`), 테스트·MkDocs strict build·브라우저 홈→목록→상세→원문 검증을 수행합니다.

## 조사 완료 기준

- 후보 원문 Markdown: 12개
- manifest: 1개
- coverage: 1개
- publication plan: 1개
- 작업 범위 밖 변경: 없음

