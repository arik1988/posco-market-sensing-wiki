# POSCO 철강 2024-08-19~2026-08-19 백필 조사 범위

## 기준과 방법

- 조사·수집 기준일: **2026-08-19**. 원문 발표일·사건일·효력일은 각 manifest에서 분리했습니다.
- 대상: POSCO 철강의 가격·원가·물량·계약·CAPEX·수출 접근성에 직접 연결되는 외부 변화.
- 시작 audit 기준값: 2026-08-19 실행 결과 `unpublished_claims=0`, `signal_schema=0`, `signal_integrity=0`, `signal_quality=0`.
- 기존 지식 중복 조회: `market_sensing.py search market-sensing-wiki --query "POSCO 철강 가격 원가 물량 계약 CAPEX 수출 2024 2025 2026" --limit 20`. 기존에는 2026 OECD 초과공급, EU 2026 철강 조치, POSCO Holdings Q2 2026, CBAM 일반 페이지가 확인되어 해당 사건은 신규·후속 차이 여부를 manifest에 적었습니다.

## 검색 쿼리

1. `site:whitehouse.gov 2025 proclamation steel aluminum tariffs 50 percent June 4 2025`
2. `site:ec.europa.eu steel safeguard 2025 quota 0.1%`
3. `China MIIT steel capacity replacement pause August 2024`
4. `European Steel and Metals Action Plan March 2025 official`
5. `Korea ETS Phase 4 allocation steel 2026 2030 official`
6. `China steel work plan 2025 2026 value added 4 percent official`
7. `India DGTR final findings flat steel safeguard August 2025`
8. `Korea MOTIE carbon neutral leading plant support 2025`

## 확인·선정 후보

| 후보 | 확인한 1차 원문 | 사업 연결 | 선정 이유 |
| --- | --- | --- | --- |
| 중국 생산능력 치환 중단 | 중국 MIIT 공고, 2024-08-20 | 경쟁 공급·가격 | 증설 승인 경로를 직접 변경 |
| 미국 Section 232 50% | 백악관 포고령, 2025-06-03 | 미국 수출·계약 | 2025-06-04 즉시 효력의 관세 충격 |
| EU 세이프가드 강화 | EU 집행위, 2025-03-25 | EU 쿼터·물량 | 자유화율·이월·재배분 규칙 변경 |
| EU 철강·금속 행동계획 | EUR-Lex COM(2025)125 | 저탄소 CAPEX·수요 | 에너지·탈탄소·무역정책을 묶은 전략 기준 |
| 한국 탄소중립 선도플랜트 지원 | 산업부 공고 2025-335 | 국내 CAPEX·공급망 | 수출 탄소경쟁력 지원 창구 |
| 한국 ETS 4차 할당 | 기후에너지환경부, 2025-11-11 | 탄소 원가·감축투자 | 2026~2030 철강 무상할당 원칙·총량 확정 |
| 중국 철강 2025~26 계획 | 중국 정부망/MIIT, 2025-09-22 | 범용·고급재 경쟁 | 고급화·퇴출·녹색투자 병행 |
| 인도 평강 세이프가드 권고 | 인도 DGTR 최종 PDF, 2025-08-16 | 인도 수출 접근성 | 12%→11.5%→11% 권고와 한국산 수입 통계 |

## 제외·중복·접근 실패

- **EU 2026년 18.3Mt/50% 규정 단독 후보 제외:** 기존 저장 지식의 `EU steel measure`가 동일 2026-06-30 정책을 이미 보존하고 있어 신규 사건으로 만들지 않았습니다. 다만 2025-03 강화는 별도 조정 이벤트로 선정했습니다.
- **EU CBAM 일반 definitive regime 제외:** 기존 지식에 동일 일반 페이지가 있어 중복 가능성이 높았습니다. 2025년 단순화·50t 면제는 별도 후속 후보로 필요하면 추가 검토합니다.
- **중국 2024-11 수출세 환급 조정 제외:** 공식 공고가 알루미늄·구리·배터리 중심으로 철강을 직접 대상으로 하지 않아 POSCO 철강 신호로 선정하지 않았습니다.
- **POSCO·Vale 등 회사 보도자료 일부 제외:** 회사 자체 발표는 외부 변화의 독립 근거가 아니거나 기존 투자 기록과 중복돼 이번 8개 최소 세트에는 넣지 않았습니다.
- **접근 실패:** 최종 실패 URL은 없음. 중국어 원문·인도 PDF는 일반 HTTP/문서 본문 확인에 성공했고, 로그인·유료벽·robots 우회는 하지 않았습니다.

## 후속 검증 계획

각 후보는 정책 발표 사실과 POSCO의 실제 물량·계약·CAPEX 영향을 분리했습니다. 다음 단계 ingest 전에 ① 당시 후속 통지·실제 효력, ② POSCO 품목별 노출, ③ 가격·물량·원가 내부값을 대조해야 합니다. 2026-08-19 현재 자료는 과거 시점의 의사결정 후보 재구성이며, 현재 제도 상태가 바뀐 항목은 기존 후보의 `effective_date` 이후 후속 원문으로 갱신해야 합니다.
