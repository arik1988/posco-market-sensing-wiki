# Market Sensing Intelligence 저장소 지침

- 조사·검색·보고 전에 상위 `WIKI-SETTINGS.md`를 읽으세요.
- 조사 결과를 저장하는 작업은 Source·Claim에서 끝내지 말고 `add-signal`로 한 문장,
  문단 Insight, 문서급 상세 분석을 연결한 뒤 MkDocs 화면까지 검증하세요.
- Signal 상세 분석은 같은 페이지에 인라인 표시하며 별도 보고서 링크로 대신하지 마세요.
- Signal 작성 전 `../skills/market-sensing-intelligence/references/signal-analysis-template.md`를
  읽으세요.
- 정량화 가능한 Signal은 공개정보와 합리적 대용변수를 사용해 영향액을 숫자로 먼저
  제시하고 방어·기준·압박 시나리오를 만드세요. 핵심 가정 3~8개는 근거·단위·범위를
  가진 슬라이더와 직접입력으로 조정되게 하고 `set-impact-estimate`로 연결하세요.
- 총노출액과 순영향액을 구분하고 가격·물량·원가·계약 전가·대응비용을 사업이론에 맞게
  분해하세요. 회사 실제값이 아니면 낮은 신뢰도와 넓은 범위를 명시하고 중복효과를
  합산하지 마세요.
- 일반 운영에서는 `.system/raw/`의 등록 원문을 수정하거나 삭제하지 마세요. 사용자가 컨셉 전환을 위한 전체 초기화를 명시적으로 승인한 경우에는 Source·Claim·원문·파생 문서를 함께 삭제하고 빈 저장소로 재생성할 수 있습니다.
- 수치·날짜·일정·투자비·용량은 `.system/claims/`의 원자적 claim으로 관리하세요.
- 기존 주장과 다른 값은 자동 덮어쓰지 말고 `.system/reviews/pending/`으로 보내세요.
- 오래된 정보는 삭제하지 말고 `superseded`, `disputed`, `cancelled`, `stale`로 전환하세요.
- `index.md`, `REVIEW.md`, 회사·기술·프로젝트·출처 문서는 자동 생성본입니다.
- 사실과 AI 분석을 분리하고 모든 핵심 사실은 내부 Claim과 Source로 추적하세요.
  MkDocs 본문에는 Claim ID·predicate·raw 경로 같은 시스템 필드를 노출하지 마세요.
- MkDocs 탐색에는 프로젝트별 문서를 독립 메뉴로 노출하지 마세요. `recent-updates.md`는
  원자 Claim 변경표가 아니라 발행된 Signal의 평가일·정보 발표일·영향도·긴급도만 보여주는
  사람용 화면이어야 합니다.
- 설비·공정 이미지가 필요하면 `add-image`로 Source에 연결하고 원문·캡션·유형·권리 상태를 기록하세요.
- 권리가 불명확한 이미지는 복제하지 말고 `link_only`로 원문 링크만 보존하세요.
- 검색 범위, 쿼리, 접근 실패를 `.system/runs/`에 기록하세요.
