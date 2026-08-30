# 데이터 계약

## 저장 매체 계약

모든 프로그램 산물의 유일한 정본은 `data/market_sensing.db`입니다. 아래 계약에서
`.system/.../*.json`, `.system/raw/...`, `reports/.../*.md`처럼 보이는 경로는 기존 ID와
collection을 설명하기 위한 **논리 주소**일 뿐 실제 파일을 만들지 않습니다.

- 구조화 레코드: `wiki_records(collection, record_id, payload_json, ...)`
- 불변 원문: `wiki_source_contents(source_id, content BLOB, raw_sha256, ...)`
- 이미지: `wiki_binary_assets`
- 감사·브리프·보고서·이벤트: `wiki_artifacts`의 Markdown/HTML TEXT
- 설정 캐시와 로그: `wiki_settings`, `wiki_operation_log`
- 분석 정규 테이블: `wiki_source_assets`, `wiki_risk_factors`,
  `wiki_claim_versions`, `wiki_observation_versions`, `wiki_event_versions`,
  `wiki_signal_versions`, `wiki_signal_evidence`, `wiki_risk_factor_links`,
  `wiki_company_impact_versions`, `wiki_scenario_versions`
- 사용자별 선택 상태: `wiki_signal_favorites(user_key, signal_id, favorited_at)`
- MyPIN 전문가 의견: `wiki_signal_comments(comment_id, signal_id, source_system,
  source_comment_id, stance, decision_deadline, ...)`
- 반복 조사 운영 설정: `wiki_research_schedules(schedule_id, payload_json, enabled,
  next_run_at, created_at, updated_at)`

`MYPIN_DATABASE_PATH`가 지정되면 그 한 파일을 사용하고, 없으면 저장소 아래
`data/market_sensing.db`를 사용합니다. SQLite 밖의 개별 Markdown·JSON·원문 파일은
정본도 호환 투영본도 아닙니다. 이 절과 충돌하는 아래의 과거 파일 경로 설명은 레코드
형식과 collection 명칭만 해석하고 저장 방식으로 사용하지 않습니다.

사용자가 Signal 이외 데이터 제거를 명시적으로 승인한 경우 `prune-to-signals`는
`signals → insights → claims → sources → wiki_source_contents`의 참조 폐쇄를 먼저
계산합니다. Insight의 `analysis_structured`와 `analysis_markdown`은 각각 신호분석과
보고서이므로 모두 보존합니다. 연결 Claim의 이력 관계와 Source revision 관계까지
보존한 뒤 미연결 레코드, run, review, 별도 artifact와 운영 로그를
하나의 트랜잭션으로 제거합니다. 실행 전 SQLite 온라인 백업, 실행 후 VACUUM·WAL truncate,
무결성 검사와 전체 Signal 브라우저 검증이 필수입니다.

다른 프로그램에 전달하는 산출물은 SQLite 파일 하나뿐입니다. 기계가 재사용할 수 있는
내용은 가능한 한 `wiki_records.payload_json`에 명시적인 키·타입·배열·객체를 가진 JSON으로
구조화합니다. ID·조회·관계·무결성 제약은 정규 SQLite 컬럼에 두고, 원문·이미지는 BLOB,
사람용 Markdown·HTML은 DB TEXT로 저장합니다. JSON·Markdown 파일을 명령 입력으로 사용할
수는 있지만 임시 입력으로만 취급하며 SQLite 밖에 영속 산출물로 남기지 않습니다.

HTTP로 다른 프로그램에 DB를 전달할 때도 같은 계약을 유지합니다. 실행 중인 원본 파일이나
WAL 보조 파일을 직접 복사하지 않고 SQLite online backup으로 단일 snapshot을 만든 뒤
`integrity_check` 성공본만 전송합니다. 응답에는 생성 시각과 SHA-256을 포함하며 전송용
임시 파일은 영속 산출물로 남기지 않습니다. 조사 시작 API는 검증된 구조화 입력만 받고
기존 직렬 실행 큐를 사용합니다. 공용 운영 API도 등록된 명령과 인자 schema만 허용하고
임의 셸·작업 디렉터리·파일 경로를 입력으로 받지 않습니다. UTF-8·base64 임시 입력은
격리 디렉터리에만 만들고 작업 뒤 삭제합니다. 파괴적 작업은 명시적 확인값과 서버 관리
backup을 요구합니다.

관심 범위의 정본 편집면은 `WIKI-SETTINGS.md`의 `우선 기업`과 `우선 회사·사업축`입니다.
후자는 `회사 | 사업축`의 대응을 보존하며 API 응답에서는
`company_axes: [{company, business_axis}]`로 표현합니다. 설정 API는 두 섹션을 원자적으로
갱신하고 같은 요청 안에서 SQLite `wiki_settings`의 `watchlist` 캐시를 동기화합니다.
조사 요청에 명시적 범위가 없을 때만 이 등록 범위를 기본값으로 사용합니다.

Signal 좋아요는 canonical Signal의 사실·평가 데이터와 분리한다. `user_key`는 인증
시스템이 만든 128자 이하의 불투명 식별자이며 이름·사번·이메일을 직접 사용하지 않는다.
`signal_id`는 `wiki_records(collection='signals')`에 실제 존재해야 하고, 사용자와 Signal의
복합 키는 같은 좋아요의 중복 등록을 막는다. 좋아요 해제는 행 삭제로 표현하며 Signal이나
Insight는 변경하지 않는다. Signal이 명시적으로 삭제되면 연결 좋아요도 함께 정리된다.
API의 등록·해제는 반복 호출에 같은 최종 상태를 보장해야 하며 목록은 `favorited_at` 최신순으로
반환한다.

Signal 전문가 의견은 canonical Signal의 Source·Claim·AI 평가와 분리한다. 다른 PC의
MyPIN이 보내는 댓글은 전용 API로 원본 키를 유지해 동기화하며, 이 저장소에서 예시 댓글을
생성하지 않는다.

- `comment_id`는 snapshot 안의 댓글 식별자이고, `signal_id`는 실제
  `wiki_records(collection='signals')` 행을 참조한다.
- `(source_system, source_comment_id)`는 원본 MyPIN 댓글의 멱등 동기화 키다.
- `parent_comment_id`는 같은 테이블의 댓글을 선택적으로 참조해 답글 계보를 보존한다.
- `author_user_key`는 원본 인증 경계의 안정 키이며, `author_display_name`,
  `author_company`, `author_department`는 댓글 작성 당시의 화면 표시 snapshot이다.
- `stance`는 `agree`, `skeptical` 중 하나다. `decision_deadline`은 확인된 `YYYY-MM-DD`만
  저장하고 미기재는 임의 날짜가 아니라 `NULL`로 둔다.
- `source_created_at`, `source_updated_at`, `imported_at`을 분리해 원본 작성·수정 시각과
  SQLite 반입 시각을 혼동하지 않는다. 추가 원본 필드는 유효한 `metadata_json`에 둔다.
- 의견 2건, 동의 1건·회의적 1건, 평균 결정기한 같은 화면 값과 AI 논의 요약은 이 원문
  행에서 파생한다. 파생 결과를 Signal 또는 댓글 본문에 덮어쓰지 않는다.
- Signal 삭제 시 댓글은 함께 정리되지만 Signal version 교체나 점수 재평가로는 삭제하지 않는다.

반복 조사 일정은 조사 결과나 Signal 평가가 아닌 로컬 운영 설정이다. 일정별
`payload_json`에는 조사 주제, 회사·사업축, Provider, Codex 모델·effort, SQLite 발행 여부, `daily|weekly|monthly`
주기, Asia/Seoul 실행 시각, 최근 재탐색 일수, 활성 상태, 마지막·다음 실행을 구조화해
저장한다. 고정된 `date_from`·`date_to`를 반복하지 않고 실행 시점에 `lookback_days`로
기간을 계산한다. 월간 실행일은 1~28일만 허용하며 만기 일정은 같은 SQLite를 쓰는 다른
조사와 함께 직렬 실행한다. 서버가 중단된 동안의 모든 누락 회차를 몰아서 실행하지 않고,
재시작 뒤 가장 가까운 다음 실행 시각으로 전진시켜 중복 발행을 막는다.

Codex 일정의 `codex_model`은 `gpt-5.6-sol|gpt-5.6-terra|gpt-5.6-luna`,
`codex_effort`는 `light|medium|high` 중 하나다. 사람 화면은 각각 `GPT-5.6-Sol`과
`Light`처럼 표시하며 실행 어댑터에서만 `light`를 Codex runtime의 `low`로 매핑한다.
새 요청의 기본값은 `gpt-5.6-luna`와 `medium`이다.

즉시 실행과 반복 일정은 조사 주제의 필수 1차 대상 회사를 `topic_company` 문자열로
저장한다. 이 값은 `company_axes`의 회사 중 하나여야 하며 Agent 요청에도 그대로 전달한다.
사용자 지정 범위는 `company_axes` 배열로 저장하며 각 원소는
`company`와 `business_axis` 문자열을 함께 가진다. 둘의 대응을 잃는 독립 배열만 정본으로
사용하지 않는다. 설정된 우선 회사·사업축은 UI 시작값과 이전 `companies` 입력의 호환
매핑일 뿐이며, 사용자가 직접 입력한 회사·사업축 조합도 같은 검증을 거쳐 보존한다.

## Signal Analytics 공통 의미 모델

Signal은 기사 1건, 문서 1건, 지표 1개가 아니라 **의사결정에 의미가 있는 시장 상태의
변화(canonical market change)**다. 기사·공시·정책·가격·환율·재고·운임·AIS·위성·관심도는
Signal 자체가 아니라 Claim·Event·Observation 형태의 Evidence다. Evidence는 발행 전에
`risk_factor_id`로 분류되고, 발행 시 하나의 안정적인 `signal_id` 아래 결합된다.

- `signal_id`: `canonical_key`에서 결정되는 변화의 안정 ID. 평가일·점수·문구 변경으로
  바뀌지 않는다.
- `signal_version_id`: Evidence·판단·평가시점이 달라질 때 추가되는 불변 버전 ID다.
- 기존 SQLite 스냅샷을 현재 계약으로 올릴 때는 `migrate-analytics-contract`를 사용한다.
  이 명령은 원본 DB를 먼저 백업하고 기존 `signal_id`를 유지한 채 Source modality,
  Claim version, Risk factor, Evidence ref와 Signal version을 한 번에 생성한다.
- `risk_factor_id`: Observation·Event·Claim·Signal이 공통으로 사용하는 관리형 분류 키다.
  `RF-UPPER-KEBAB` 형식이며 이름·정의·category·taxonomy version을 별도 관리한다.
- `source_modality`: Source의 정보 생성 방식을 나타내며 `MARKET`, `DOCUMENT`, `PHYSICAL`,
  `ATTENTION` 중 하나다. `source_type`의 발행주체·문서종류 분류와 독립된 축이다.
- `EvidenceRef`: `kind=claim|event|observation`, 해당 불변 `version_id`, `modality`,
  `relation=support|contradict|context`, 원 Source ID를 보존한다.
- `CompanyImpactVersion`과 `ScenarioVersion`은 Signal 본체와 분리해 동일한 시장 변화가
  회사·사업축별로 다른 영향과 조건부 대응을 갖게 한다.

정형 지표 수집 DB와 Agent 수집 DB는 물리적으로 분리할 수 있다. 단, snapshot 경계에서는
Observation과 Document/Event/Claim이 동일한 `risk_factor_id` 및 불변 evidence version ID를
제공해야 하며, 단일 SQLite의 `signal_version_id`에서 합쳐져야 한다. 제목 유사도나 평가일로
Signal identity를 다시 만들지 않는다.

### 지표 ID와 시간 계약

- `indicator_id`는 adapter·분석 출력·소비 화면이 공통으로 참조하는 논리 지표 ID다.
  MVP에서는 기존 `market_indicator_series.series_key` 값을 그대로 사용한다. 예시는
  `raw_material.iron_ore_62_futures`처럼 소문자 점 구분 namespace와 snake_case 지표명이다.
  `series_key`와 별개의 병렬 ID를 새로 만들지 않으며, 기존 정규 컬럼명이 `series_key`이면
  그 값의 의미를 `indicator_id`로 해석한다.
- 분석 block은 최소한 `indicator_id`와 불변 `observation_version_id`를 함께 참조한다.
  MVP에서는 별도 지표 연결 테이블을 강제하지 않는다. typed JSON의 `indicator_id` 참조와
  `wiki_systematic_analysis_inputs`의 Observation version 관계로 데이터 레벨 연결을 만든다.
- `observed_at`은 원 지표가 가리키는 관측·기준시점이다.
- `detected_at`은 우리 시스템이 해당 불변 Observation version을 처음 성공적으로 확보해
  알게 된 시각이다. 사람 화면의 `감지일`·`감지시각`과 lead time 계산은 이 값을 사용한다.
  timezone을 포함한 시각을 보존하고 재수집이나 재적재 때 덮어쓰지 않는다.
- `collected_at`은 각 수집 시도 또는 revision을 확보한 시각이다. 같은 관측치를 다시
  수집하면 새 수집 이력에 추가되며 최초 `detected_at`을 바꾸지 않는다.
- `ingested_at`은 수집과 SQLite 커밋이 분리될 때만 기록하는 저장 완료 시각이다.
  `detected_at`의 대체값으로 사용하지 않는다.
- 정정값이나 새 revision은 새 불변 Observation version과 그 version의 `detected_at`을
  가진다. 논리 Observation의 최초 감지시각은 모든 version의 `detected_at` 최솟값이다.
- Signal 수준의 `detected_at`은 Evidence를 처음 Signal로 승격해 판단한 시각이다.
  Observation 수준의 `detected_at`보다 늦을 수 있으며 두 값을 같은 필드 의미로 합치지
  않는다. `assessed_at`은 재평가 시각이므로 Signal 감지시각을 덮어쓰지 않는다.

### Systematic Analysis Version

정량 분석이 적합하고 검증된 시계열 Observation이 충분한 Signal에만
`systematic_analyses` collection과 `wiki_systematic_analysis_versions`를 선택적으로 둔다.
별도 DB나 별도 Signal을 만들지 않는다. `wiki_systematic_analysis_inputs`는 결과가 사용한
각 `observation_version_id`·`risk_factor_id`·`series_key`를 정규 관계로 고정하며,
이때 `series_key` 값은 위에서 정의한 `indicator_id`와 같다.

- `analysis_result_version_id`, `analysis_id`, `version_no`: 결과의 불변 버전과 안정 ID
- `signal_version_id`: 계산 당시의 canonical Signal version. 현재 Signal이 갱신되어도
  과거 계산을 덮어쓰지 않는다.
- `analysis_scope.kind`: 하나의 변화는 `atomic`, 둘 이상의 독립 Signal 결합효과는
  `interaction`이다. interaction은 `component_signal_version_ids`를 두 개 이상 명시한다.
  복합 현상을 표현하기 위해 원자 Signal의 사실 경계를 억지로 합치지 않는다.
- `method_bundle`: `formula_revision`, `historical_window_policy_revision`,
  `feature_set_revision`, `normalization_revision`, 계산 parameter를 모두 명시한다.
- `input_observation_version_ids`: 검증된 수치 Observation version만 허용한다. 임시 웹 값,
  출처 없는 수치, AI가 보완한 수치는 금지한다.
- `results`: robust anomaly, 두 window의 관계 변화, 상관 network 변화, Shannon entropy
  변화, Risk Factor contribution candidate를 typed JSON으로 저장한다.
- `status`: 한 가지 이상 계산되면 `completed`, 최소 표본을 충족하지 못하면
  `insufficient_data`다. 후자의 누락값을 추정해 채우지 않는다.
- `content_digest`: ID·생성시각과 분리된 의미 payload의 canonical JSON SHA-256이다.
  `audit`은 저장된 Observation과 method bundle로 재계산해 동일성을 확인한다.

Insight에는 UI용 경량 `systematic_analytics` projection만 선택적으로 두고 정본 결과 ID를
가리킨다. 화면은 이를 기존 신호분석의 키 드라이버 근거로 표시하며 원인 확정, 예측 확률,
별도 신뢰점수로 바꾸지 않는다. business Scenario와 원가 What-if simulator는 여전히
“더 움직이면 무엇이 달라지는가”를 다루며, 이 계산 레이어의 “무엇이 달라졌는가”와
역할을 섞지 않는다.

## Signal과 Insight

`wiki_records`의 `signals` collection schema v4는 canonical identity, Evidence,
RiskFactor, 변화 유형, 사업 시사점, 1~10점 점수·평가시점을 보존한다.
`insights` collection schema v3는 관측 변화 제목, 문단 해석, UI용 구조화 분석 JSON과
읽기용 문서급 Markdown을 함께 보존한다. 신규 계약은 이전 schema를 dual-read하지 않으며
개발 snapshot은 v4/v3로 다시 발행한다.
`insight_id`로 연결하며 Insight는 다시 `claim_ids`, `source_ids`, `document_path`를 통해
Claim·Source·Archive로 이어진다.

Signal의 `signal_type`은 다음 8개 값 중 정확히 하나다.

- `정책·규제`
- `수급·가격`
- `경쟁사`
- `투자·프로젝트`
- `공급망·물류`
- `고객·계약`
- `기술·운영`
- `재무·실적`

신규 발행 Signal은 `signal_role`과 `signal_origin`도 반드시 가진다.

- `signal_role`: `core_market_signal` 또는 `execution_context`
- `signal_origin`: `external_market`, `policy_regulator`,
  `competitor_counterparty`, `company_execution`
- `core_market_signal`에는 앞의 외부 발생원 세 개만 허용한다.
- `execution_context`에는 `company_execution`만 허용한다.
- 대상 회사·자회사의 `company_release`·`company_ir`만 연결된 실행 사실은
  `core_market_signal`로 저장하지 않는다.

신규 `core_market_signal`은 `assumption_challenge` schema v1도 필수다.

- `baseline_assumption`: 현재 계획이 암묵적으로 전제하는 수요·원료·접근·원가 조건
- `observed_break`: 그 전제를 약화시키는 검증된 외부 행동 또는 규칙
- `decision_change`: 관측이 지속될 때 실제로 바꿀 제품·계약·투자·운영 판단
- `pattern`: 허용된 8개 전제변경 패턴 중 하나
- `surprise_score`: 기존 정보와 결정의 거리를 나타내는 1~5점. 흥미 점수가 아님
- `falsification_check`: 이 해석을 약화시키거나 폐기할 구체적 확인 한 가지

`add-signal`이 외부 핵심 시그널을 발행하면 run의 `discovery_contract.version=1`과
적용 Signal ID를 기록한다. `audit`은 계약 대상 Signal에서 이 구조의 누락을 오류로 본다.

```json
{
  "schema_version": 4,
  "signal_id": "SIG-...",
  "signal_version_id": "SIGV-...",
  "version_no": 1,
  "canonical_key": "eu.steel.low-carbon-procurement",
  "risk_factor_ids": ["RF-EU-LOW-CARBON-PROCUREMENT"],
  "evidence_refs": [
    {
      "kind": "event",
      "version_id": "EVTV-...",
      "modality": "DOCUMENT",
      "relation": "support",
      "source_ids": ["SRC-..."]
    }
  ],
  "signal_type": "정책·규제",
  "signal_role": "core_market_signal",
  "signal_origin": "policy_regulator",
  "sentence": "EU 조치로 고객별 계약 갱신일과 가격 전가 범위를 다시 확인해야 합니다.",
  "business_axis": "철강",
  "business_impact": {
    "score": 9,
    "rationale": "시장접근과 현지 생산 전환의 경제성이 중대하게 바뀝니다."
  },
  "urgency": {
    "score": 8,
    "rationale": "시행 중인 규칙을 현재 계약과 통관계획에 즉시 반영해야 합니다."
  },
  "insight_id": "INS-..."
}
```

사람 화면에서는 `business_axis`와 `signal_type`을 각각 하나의 pill로 표시한다. 회사명,
점수, 평가일과 내부 canonical ID는 pill 분류에 섞거나 노출하지 않는다.

schema v4의 `business_impact.score`와 `urgency.score`는 1~10 정수다. `score_scale`은
`version=1`, `minimum=1`, `maximum=10`, `calibration`을 보존한다. 구간은 1~2 관찰,
3~4 제한적 영향, 5~6 관리 필요, 7~8 경영 판단 필요, 9 중대한 의사결정 영향,
10 전사 손익·핵심 사업 지속성·대규모 자본배분에 되돌리기 어려운 손실을 만들 수 있어
절대 놓쳐서는 안 되는 파급력의 예외 상황이다. 사업영향도 10점과 긴급도는 독립 축이므로
파급력 10점의 대응 시한이 상대적으로 길 수도 있다. 10점은 일반적인 고영향 Signal의
상위 표현이 아니며 파급 범위·손실 규모·전파 속도·불가역성 근거가 있어야 한다. 점수 분포는 구분력
점검에 사용하되 분포를 맞추기 위한 강제 할당은 하지 않는다. 기존 1~5점은
`migrate-signal-scores`로 1·3·5·7·8 기준점에 이관하고 9~10점을 자동 부여하지 않아
점수 인플레이션을 막는다.

완료 run은 최대 점수를 기준으로 1~4점 관찰군과 5~7점 관리군을 각각 20% 이상,
8~10점 경영군을 50% 이하로 점검한다. 표본이 3건 이상이면 같은 정수 점수가 50%를
초과하는지도 점검한다. 실제 유효 사건이 적어 축별 최소 건수에 미달하면
`documented_axis_gaps`에 `axis`, `actual_signals`, 구체적 `reason`, `next_trigger`를 남긴
경우에만 건수 경고를 해소하며, 점수 분포를 맞추기 위한 강제 할당은 금지한다.

두 점수의 `rationale`은 각각 독립 필드이며 UI 전달 JSON에서도 같은 중첩 구조를
유지한다. 목록과 상세 화면은 해당 점수에 마우스를 올리거나 키보드로 포커스했을 때
그 점수의 `rationale`만 도움말로 표시한다. 렌더러가 두 근거를 합치거나 산문에서
재추출해 만들지 않는다.

신규 발행과 재평가의 각 `rationale`은 120~600자, 3~4문장이어야 한다. 확인된 변화·상태,
회사 영향 경로와 해당 점수, 인접 점수와의 경계를 순서대로 설명하고 본문에 실제 점수
표현(예: `7점`)을 포함한다. 긴급도는 확인된 시한 또는 다음 평가 조건과 그 전에 할 일을
함께 적는다. 단순 명사구, `중요함`, `확인 필요`, 날짜와 할 일만 적은 문장은 유효한
판정 사유로 보지 않는다.

`add-signal`은 `canonical_key`, 하나 이상의 `risk_factor_id`, 하나 이상의 version-pinned
Evidence를 필수로 받고 `signal_contract.version=2`를 기록한다. 이 필드가 없는 개발
snapshot은 자동 추정하지 않고 audit 및 MyPIN importer에서 거부한다.

사람용 필드는 다음 편집 계약을 함께 만족해야 한다.

- `Insight.title`: 8~45자, 관측된 변화 중심의 짧고 평이한 사실형 제목, 서술형 존댓말
  종결과 헤드라인식 말줄임표 금지
- `Signal.sentence`: 20~180자, 제목과 분리해 회사의 사업영향과 달라지는 판단을 설명하는
  완전문장형 `사업 시사점`
- `Insight.summary`: 70~500자, 마침표로 구분된 2~4문장으로 무슨 일·회사 영향·지금
  판단을 평이한 한국어로 설명
- 제목에는 설명 없는 램프업·게이트·트리거·자본규율·공급곡선 같은 번역투나 내부
  메모 용어를 쓰지 않는다. 회사명·사업축·변화 유형·사업영향을 제목 하나에 반복해
  넣지 않는다. 구체 기준은 `editorial-style.md`를 따른다.

Insight는 `analysis_structured`와 `analysis_markdown`을 같은 `payload_json` 안에 둔다.
`analysis_structured` schema v3는 UI가 문자열을 재파싱하지 않고 표·목록·흐름을 만들기
위한 기계 판독 표현이며 다음 계약을 따른다.

- 최상위는 `schema_version=3`, 순서가 보존되는 `sections` 배열을 가진다. 이전 schema는
  신규 snapshot에서 허용하지 않는다.
- 각 section은 고유한 lower snake_case `key`, 화면 제목 `title`, `items` 배열을 가진다.
- 신규 데이터는 `scenarios`, `business_impact`, `key_drivers`, `evidence`,
  `falsification_actions` 다섯 section을 필수로 가진다.
- 각 item은 고유한 `key`, 사용자용 `label`, `display(text|list|table|flow)`를 가진다.
- `text`는 `value`, `list`는 문자열 `items`, `flow`는 3개 이상의 `steps`, `table`은
  `columns(key,label)`와 열 키가 일치하는 `rows`를 가진다.
- 모든 점수대의 최소 의미 키에는 판단 질문·잠정 결론·확인된 변화·영향 경로·3개
  시나리오·관찰 지표 외에도 기회·위험·기회비용, 정량화 판정, 상향·하향 트리거,
  발표·효력·판단 시점, 기존 전제·바꿀 결정, 반증 조건, 내부 데이터·담당·재탐지 조건,
  다음 산출물과 한계를 포함한다.
- `scenarios`, `monitoring_indicators`, `opportunity`, `risk`, `quantification_decision`,
  `escalation_triggers`, `deescalation_triggers`, `timing`은 열 의미가 고정된 표로 저장한다.
  시나리오는 3행, 관찰 지표는 3행, 상향·하향 트리거는 각각 2행 이상이어야 한다.
- 작성 중요도 5~7점에는 `secondary_effects`, `response_options`, `sensitivity_drivers`,
  `execution_sequence`를, 8~10점에는 `delay_loss`, `reversibility`,
  `strongest_counterevidence`, `decision_authority`, `confirmed_deadline_or_condition`을
  추가한다. `audit`은 Signal 두 점수 중 큰 값을 기준으로 이 깊이를 검증한다.
- item의 선택 `claim_ids`, `source_ids`는 해당 Insight에 실제 연결된 ID만 참조한다.

`analysis_markdown`은 MyPIN Signal 상세의 산문 탭에 렌더링되는 3단계 본문이다. 첫 비어
있지 않은 줄은 해당 Signal의 결론을 드러내는 `##` 주요 장 제목이어야 하며, 그 앞에
제목 없는 리드 문단이나 Signal 제목을 반복한 `#` 제목을 두지 않는다. 첫 장의 도입
문단은 결론과 뜻을 평이한 한국어로 설명하고, 다음 의미 단위와
근거·수치·시나리오의 깊이는 그대로 유지해야 한다.

`##`~`####` 장 제목은 본문 문장과 달리 전문 리서치 보고서의 압축 헤드라인으로 쓴다.
짧은 명사형·서술형을 사용하고 `~합니다`, `~됩니다`, `~입니다`처럼 독자에게 설명하는
경어 종결이나 마침표를 붙이지 않는다. 본문은 기존 존댓말 문체를 유지한다.

- 확인된 변화와 시점
- 회사에 전달되는 사업 영향 경로
- 조건부 사업 시나리오
- 지금 확인할 지표
- 의사결정에 필요한 다음 산출물
- 판단의 한계

두 분석 표현의 작성 중요도는 저장 필드를 추가하거나 두 점수를 합산하지 않고
`max(business_impact.score, urgency.score)`로 계산한다. 중요도가 높을수록
`analysis_structured`의 각 section에 의사결정에 필요한 분기·대안·근거·반증·실행 항목을
늘리고, `analysis_markdown`도 같은 판단 깊이를 산문으로 확장한다. 한 표현에만 상세 내용을
두지 않는다. 권장 본문 목표는 근거가 충분한 경우 1~4점 1,200자 이상, 5~7점 1,800자
이상, 8~10점 2,500자 이상이다. 글자 수는 품질의 대리값일 뿐 스키마 유효성 조건이 아니며,
근거가 부족할 때 반복·일반론·추정값으로 채우지 않고 부족한 입력과 재검토 조건을 기록한다.

MkDocs 투영에서 두 탭이 공유하는 것은 회사·사업축·변화 유형, 제목, 사업 시사점,
사업영향도, 긴급도, 감지일, 평가일까지다. 그 직후부터 전체 본문을 두 탭으로 나누며
`판단 요약`, `왜 중요한가`, Insight summary, 점수 근거를 탭 위 공통 본문으로 렌더링하지
않는다. 구조화 탭은
`1. 시나리오 → 2. 사업 영향 → 3. 키 드라이버 → 4. 근거와 시점 → 5. 반증과 다음 행동`을
렌더링한다. 산문 탭은 `analysis_markdown`의 자연스러운 결론형 장 구성을 그대로 사용하며,
구조화 탭의 목차나 `판단 요약/왜 중요한가/상세 분석`을 다시 붙이지 않는다. 연결 근거와
원문은 두 표현이 공유하는 탭 아래 영역이다.

Signal 페이지는 다른 보고서 링크를 상세 분석의 대체물로 사용하지 않는다. 내부 JSON의
Signal·Insight·Claim ID, 해시, raw 경로는 MkDocs 본문에 노출하지 않는다. Source 원문
링크와 보관 원문은 마지막 단계에서 사람이 읽을 수 있는 명칭으로 표시한다.

Insight의 `quantification_decision`은 모든 신규 Signal의 What-if 판정을 저장하는 필수
JSON 객체다. `schema_version`, `status`, `assessed_at`, `basis`를 공통으로 가지며
`status`는 `modeled` 또는 `not_applicable`만 허용한다.

- `modeled`는 같은 Insight의 검증된 `impact_estimate`를 반드시 참조한다. 내부값 비공개나
  정확한 단일값 부재는 이 상태를 포기할 사유가 아니며 넓은 범위와 낮은 신뢰도로 표현한다.
- `not_applicable`은 주제가 정량 영향·운영량·비용·수익·일정 민감도와 본질적으로 맞지 않는
  `subject_not_quantifiable` 또는 동일 충격의 중복계상을 막는 `duplicate_impact_model`만
  허용한다. `required_inputs`, `reconsider_when`을 저장하고 중복모델이면
  `related_signal_ids`에 대표 Signal을 하나 이상 연결한다.
- `deferred`, `내부 입력 대기`, 빈 문자열, 판정 누락은 허용하지 않는다. 구조화 분석의
  `quantification_decision` 표에도 같은 상태를 기록하며 두 JSON 상태가 다르면 audit 실패다.

Insight의 선택 필드 `impact_estimate`는 MkDocs와 향후 웹 프로그램이 함께 사용하는
정량 영향 What-if 모델이다. `title`, `description`, `as_of`, `confidence`, `notice`,
`formula_display`, `variables`, `outputs`, `presets`를 가진다.
기본적으로 모든 Signal에 연결하며 `quantification_decision.status=not_applicable`인
제한적 예외에만 생략한다. 이 경우 `impact_estimate`를 빈 객체나 임의의 기본값으로 채우지 않는다.

- `variables`는 3~8개 지배변수만 두고 `id`, `label`, `unit`, `min`, `max`, `step`,
  `default`, `kind`, `basis`, `source_ids`를 보존한다.
- `kind`는 `verified`, `derived`, `assumption` 중 하나다. `verified`는 Source가 필수이며
  공개되지 않은 회사값은 사실처럼 만들지 않고 `assumption`으로 둔다.
- `outputs`는 매출·EBITDA·현금흐름·NPV와 가격·물량·원가·대응비용 구성효과를 정의한다.
  정확히 하나의 `primary=true` 결과가 있어야 한다.
- `expression`은 숫자, `{ "var": "variable_id" }`, 또는 `add`, `subtract`, `multiply`,
  `divide`, `negate`의 중첩 구조로 저장한다. 이는 임의 실행 코드를 막으면서 복합 회계·경제
  산식을 그대로 표현하기 위한 계약이다.
- `presets`는 최소 방어·기준·압박 3개이며 모든 변수값을 명시한다.
- UI는 현재 입력의 주 결과값과 방어·기준·압박 프리셋의 주 결과값을 같은 결과 영역에
  상시 표시한다. 프리셋 버튼은 해당 입력값을 컨트롤에 적용하는 동작으로 유지한다.
- 결과는 회사 실제 전망이 아니라 공개정보 기반 예비 추정임을 `notice`에 밝힌다.
- 동일한 시장가격·물량 충격을 공유하는 Signal은 독립 금액처럼 합산하지 않는다.

## 목차

1. 디렉터리
2. 출처
3. 주장
4. 검토
5. 엔터티와 이벤트
6. 실행 기록과 보고서

## 1. 논리 collection

```text
project/
├── WIKI-SETTINGS.md          # 사람이 편집하는 관심사·운영 설정
└── market-sensing-wiki/
    ├── AGENTS.md
    ├── config/
    │   └── watchlist.json   # Markdown 설정의 기계용 JSON 캐시
    ├── index.md             # 사람이 보는 운영 시작 화면
    ├── REVIEW.md            # 사람이 보는 검토 대기열
    ├── companies/           # 회사 통합 문서
    ├── technologies/        # 기술 통합 문서
    ├── projects/            # 프로젝트 통합 문서
    ├── entities/            # 기타 주체 통합 문서
    ├── events/              # 사람이 보강하는 사건 노트
    ├── assets/
    │   └── media/           # 사용 권리가 확인된 Source 연결 이미지
    ├── sources/
    │   └── SRC-*.md         # 메타데이터·연결·원문 통합 페이지
    ├── .system/
    │   ├── raw/             # 일반 운영 중 불변인 원문(명시 승인된 전체 초기화 제외)
    │   ├── source-records/  # source별 JSON 메타데이터
    │   ├── source-candidates/
    │   ├── claims/          # 상태 기준인 원자적 주장 JSON
    │   ├── reviews/
    │   │   ├── pending/
    │   │   └── resolved/
    │   └── runs/            # 검색 범위·쿼리·성공/실패
    ├── reports/
    │   ├── briefs/
    │   └── audits/
    └── log.md
```

`WIKI-SETTINGS.md`가 설정의 기준이다. SQLite 설정 캐시를 직접 편집하지 않는다.
`market_sensing.py` 명령을 실행하면 Markdown 변경사항을 `wiki_settings`에 자동 반영한다. 즉시
동기화하려면 `sync-settings`, 현재 적용값을 확인하려면 `show-settings`를 사용한다.

## 2. 출처

`wiki_records`의 `sources` collection을 기준으로 한다.

```json
{
  "source_id": "SRC-20260725-A1B2C3D4",
  "title": "Project update",
  "url": "https://example.com/update",
  "canonical_url": "https://example.com/update",
  "publisher": "AIST",
  "published_at": "2026-07-21",
  "collected_at": "2026-07-25",
  "source_type": "academic",
  "language": "en",
  "reliability": "primary",
  "academic": {
    "kind": "conference_paper",
    "authors": ["A. Researcher", "B. Engineer"],
    "venue": "AISTech 2026 Proceedings",
    "doi": "10.1234/example.2026.001",
    "conference_name": "AISTech 2026",
    "conference_date": "2026-05-04",
    "conference_location": "Pittsburgh, USA",
    "peer_review_status": "peer_reviewed"
  },
  "content_sha256": "...",
  "raw_ref": "sqlite:wiki_source_contents:SRC-20260725-A1B2C3D4",
  "previous_version": null,
  "supporting_sources": [],
  "images": [
    {
      "media_id": "MED-1234ABCDEF56",
      "kind": "facility_photo",
      "caption": "실증 설비 전경",
      "alt_text": "원통형 반응기와 배관이 설치된 실증 설비",
      "creator": "Example Steel",
      "image_url": "https://example.com/media/plant.jpg",
      "origin_url": "https://example.com/update",
      "rights_status": "permitted",
      "rights_note": "공식 미디어 자료 사용 조건 확인",
      "collected_at": "2026-07-25",
      "content_sha256": "...",
      "local_path": "assets/media/SRC-20260725-A1B2C3D4/MED-1234ABCDEF56.jpg",
      "subject_ids": ["COM-EXAMPLE-STEEL", "PRJ-HAMBURG-DRI"],
      "display_width": "detail",
      "hero_priority": -100
    }
  ]
}
```

필수 필드는 `source_id`, `title`, `collected_at`, `source_type`, `language`,
`reliability`, `content_sha256`, `raw_path`다. 게시일을 알 수 없으면
`published_at`을 `null`로 둔다. 수집일을 게시일처럼 쓰지 않는다.

`source_type=academic`은 `academic.kind`가 필요하다. 허용 값은
`journal_article`, `conference_paper`, `conference_presentation`, `preprint`,
`thesis`, `research_report`다. 저자·게재지 또는 프로시딩·DOI·학회명·학회 일자·
장소·동료심사 상태는 확인되는 값만 선택적으로 기록한다. 학회 프로그램의 발표
제목만 확인되고 본문이나 초록을 확인하지 못했다면, 프로그램 자체가 입증하는
발표 사실을 넘어 기술 성능 Claim을 만들지 않는다.

기존 레코드의 학술 메타데이터를 보강할 때는 `set-academic-metadata`를 사용하며,
보관 원문의 `raw_sha256`과 `raw_path`는 유지한다. 게시일 정정은 출판사·DOI·공식
학회 자료에서 날짜를 확인한 경우에만 수행한다.

허용 `source_type`:

- `company_release`
- `company_ir`
- `government`
- `permit`
- `patent`
- `academic`
- `equipment_supplier`
- `specialist_media`
- `general_media`
- `other`

허용 `reliability`:

- `primary`: 회사·정부·특허·논문 등 원자료
- `high`: 독립적이며 근거가 분명한 2차 자료
- `medium`: 전문매체 또는 근거가 일부 확인된 자료
- `low`: 단일 익명 보도, 블로그, 출처 불명 자료

`supporting_sources`에는 재인용 URL과 매체 정보를 넣을 수 있지만 이를 별도
지식으로 계산하지 않는다.

이미지는 Source의 선택 필드인 `images`에 둔다. 허용 `kind`는
`facility_photo`, `process_diagram`, `equipment_drawing`, `patent_figure`,
`academic_figure`, `ai_reconstruction`, `other`다. 허용 `rights_status`는
`permitted`, `link_only`, `ai_generated`다.

- `permitted`: 사용 조건을 확인한 이미지를 `assets/media/`에 보관하고 해시를 기록한다.
- `link_only`: 복제 권리가 불명확해 파일을 내려받지 않고 이미지 URL과 원문만 기록한다.
- `ai_generated`: AI 재구성 파일을 보관하되 `kind`는 반드시 `ai_reconstruction`이다.

모든 이미지에는 `caption`, `alt_text`, `origin_url`, `rights_note`가 필요하다.
이미지는 기술적 사실의 독립 근거가 아니며 연결된 Source와 Claim의 보조 시각 자료다.
`subject_ids`는 해당 이미지가 표시될 수 있는 회사·기술·프로젝트 주체의 명시적
허용 목록이다. 협력·투자·컨소시엄 관계만으로 파트너의 설비 이미지를 회사 페이지에
표시하지 않는다. 특히 회사 페이지는 회사 직접 Source 또는 `subject_ids`에 해당
`COM-` ID가 명시된 이미지로 제한한다.

`display_width`는 선택 필드이며 일반 사진은 `compact`, 세부 판독이 필요한 공정도·
장치도는 `detail`을 사용한다. `hero_priority`도 선택 필드이며 작은 값이 대표 이미지
선정에서 먼저 온다. 동일 기술 페이지의 생성형 공정도를 최상단에 고정할 때는
`-100`처럼 음수 우선순위를 사용하되, 실제 설비·학술 이미지는 본문 갤러리에 함께
남겨 기술 검증 자료로 활용한다.

## 3. 주장

`wiki_records`의 `claims` collection을 기준으로 한다. 한 레코드는 한 가지 검증 가능한
명제만 표현한다.

```json
{
  "claim_id": "CLM-6F3E...",
  "subject_id": "PRJ-HAMBURG-DRI",
  "predicate": "target_start_date",
  "value": "2029 이후",
  "status": "active",
  "confidence": "medium",
  "first_seen": "2026-07-25",
  "last_verified": "2026-07-25",
  "source_ids": ["SRC-20260725-A1B2C3D4"],
  "supersedes": ["CLM-OLD..."],
  "coexists_with": [],
  "history": [
    {
      "date": "2026-07-25",
      "action": "created",
      "reason": "신규 회사 발표"
    }
  ]
}
```

허용 상태:

- `active`: 현재 유효
- `superseded`: 더 새로운 정보로 대체
- `disputed`: 출처끼리 충돌
- `cancelled`: 공식 취소
- `stale`: 재검증 기한 경과

허용 신뢰도는 `high`, `medium`, `low`다. 신뢰도는 출처 수만으로 올리지 않는다.
같은 보도자료를 인용한 여러 기사는 독립된 근거가 아니다.

사람 화면의 근거 영역은 Claim 상태와 고유 `source_ids`에서 교차검증 상태를 파생한다.
`disputed`는 `출처 상충`, 서로 독립된 Source 둘 이상은 `독립 교차확인`, Source 하나는
`단일 출처`로 표시한다. 이는 발행 차단 필드나 조사 진행 상태가 아니며, 단일 출처
Claim도 정상적인 일반 Signal에 연결할 수 있다. `추가 검증 중` 문구는 저장하거나
표시하지 않는다. 재인용 URL은 `supporting_sources`에만 있으므로 독립 Source 수에
포함하지 않는다. Source `reliability`, Claim `confidence`, 교차검증 상태는 서로
대체하지 않는다.

`subject_id` 권장 접두사:

- `COM-`: 기업
- `TEC-`: 기술
- `PRJ-`: 프로젝트
- `FAC-`: 설비
- `POL-`: 정책

`predicate`는 안정적인 영문 snake_case를 사용한다. 예:
`target_start_date`, `capex_eur`, `capacity_tpy`, `trl`, `project_status`,
`technology_route`, `funding_amount`.

## 4. 검토

`.system/reviews/pending/REV-*.json`에는 다음을 보존한다.

- 검토 유형
- 기존 claim 또는 source
- 신규 후보
- 충돌 원인
- 자동 판단을 보류한 이유
- 허용 결정

해결 후 파일을 `.system/reviews/resolved/`로 옮기고 다음을 추가한다.

```json
{
  "resolution": {
    "decided_at": "2026-07-25",
    "decision": "supersede",
    "rationale": "2026-07-21 회사 공식 발표가 기존 목표를 갱신함"
  }
}
```

결정과 근거가 없으면 해결된 것으로 처리하지 않는다.

## 5. 엔터티와 이벤트

기업·기술·프로젝트·기타 subject와 출처 페이지는 JSON에서 자동 생성되는
Markdown 투영본이다. 관련 subject와 source는 Obsidian `[[위키링크]]`로 양방향
연결한다. `<!-- AUTO-GENERATED BY market-sensing-intelligence. DO NOT EDIT. -->`가 있는
페이지, `index.md`, `REVIEW.md`를 직접 수정하지 않는다. 페이지 본문
자체를 상태의 단일 기준으로 사용하지 않는다.

기업 페이지는 사람용 보고서 계층이다. 기술의 의미, 확인된 회사 현황, 출처 문구를
바탕으로 한 단계 판단, 추가 관찰 포인트와 사람이 읽을 수 있는 출처명을 표시한다.
Claim ID, subject ID, predicate와 원자적 레코드는 `.system/`에서 관리하고 기업
페이지 본문에는 표시하지 않는다. 위키링크의 대상 파일명에는 내부 Source ID가
남을 수 있지만 Obsidian 읽기 화면에는 출처명 별칭을 보여준다.

브라우저 사용자는 Material for MkDocs로 제공되는 `index.md`에서 시작한다. 첫 화면은
사업영향도·긴급도 순 Signal과 설정된 우선 기업의 사업축을 보여주며 각 Signal은 같은 페이지 안에서
Insight·문서급 분석·원문으로 이어진다. 회사·정책·프로젝트 문서는 근거 탐색용 보조
투영본이다. 생성 Markdown을 직접 편집하지 않고 `sync-obsidian`으로 재생성한다.

이벤트는 `events/YYYY-MM-DD-<slug>.md`로 작성한다. 이벤트 유형은
`announcement`, `pilot`, `investment`, `funding`, `permit`, `partnership`,
`delay`, `suspension`, `cancellation`, `commercial_operation` 중 하나를 우선 사용한다.

## 6. 실행 기록과 보고서

`wiki_records`의 `runs` collection에 다음을 기록한다.

- 실행 시작·종료 시각
- 검색 기준일과 겹침 기간
- 기업·기술·국가·출처 범위
- 실제 쿼리
- 확인한 URL
- 접근 실패 URL
- 접근 제한 또는 재시도가 있었던 URL의 `access_attempts`
- 신규·중복·검토 후보 수
- 신규 Claim 수, 발행한 Signal 수와 Signal ID 목록
- 신규 조사 run의 `research_contract.version=1`: 조사 시작 시 설정에서 동결한 전체
  우선 회사×사업축, `mode=coverage_managed`, 셀별 최소 독립 채널 2개, 후보 목표 8건,
  수확 체감 탐색 3회. 사용자가 결과 개수를 명시하면 `mode=count_limited`와
  `target_count`를 대신 완료 기준으로 저장
- `coverage.schema_version=1`: 필수 셀별 상태·채널·탐색 전략별 수확·후보 ID·한계·다음
  트리거, 미해결 고위험 빈칸, Signal이 없는 회사의 미발행 사유와 재탐색 트리거
- 후보 장부의 `candidate_date`는 조사기간 안의 발표·사건·효력·관측일을 대표하며 일별
  Signal 귀속일 계산에 사용한다. `detected_at`은 시스템 최초 인지일이므로 과거 백필에서도
  소급하지 않는다. `research_contract.version=5`의 월간·정기 run은 날짜마다 서로 다른
  active Signal ID가 연결된 `published_signal`을 최소 3건 요구한다. 후보·watchlist·rejected와
  날짜 사이에 재사용된 같은 Signal은 일별 발행량으로 세지 않는다.
- 신규 발행 run의 `signal_contract`: 계약 버전 2, 이 계약이 적용되는 `signal_ids`,
  사업축별 외부 핵심 시그널 최소 비율 0.7, 단일 프로젝트·설비 편중 기준 0.5, 완료된
  감시 run의 사업축별 최소 Signal 3건, 최대 점수 기준 관찰군(1~4) 최소 20%, 관리군
  (5~7) 최소 20%, 경영군(8~10) 최대 50%

`results.new_claims`가 1 이상인 저장 작업은 `results.new_signals`와 `signal_ids`를 함께
기록한다. 읽기 전용 조사나 사용자가 발행을 금지한 작업이 아니라면 Claim을 만들고
Signal이 0건인 run은 미완료로 감사된다.

`research_contract.version=1`인 run은 `scout` 명령으로 시작하고 완료한다. 필수
회사×사업축이 모두 coverage에 있어야 하며, 각 셀은 적용 가능한 독립 채널 2개 이상과
고유 후보 8건 또는 최근 서로 다른 3개 탐색 전략에서 신규 고영향 후보 0건이라는 중단
근거가 필요하다. `pending`, `blocked`, 미해결 고위험 빈칸은 완료할 수 없다. 발행 Signal이
없는 회사는 구체적인 미발행 사유와 다음 재탐색 트리거가 필요하다. 완료 run에서 이 계약을
어기면 `audit`의 `research_coverage` finding으로 기록한다. 기존 복구 run에는 소급하지 않는다.

사용자가 `N개 찾아봐`처럼 결과 개수를 명시한 경우에만 `mode=count_limited`를 사용한다.
이 모드는 전사 coverage 셀과 정기 감시의 사업축별 최소 Signal·점수대 분포 조건을
적용하지 않고, `target_count` 이상의 active Signal이 해당 run에 발행됐는지 검사한다.
목표 미달은 완료 처리하지 않는다. 멀티 출처는 신뢰도 강화 요소이며 Source 한 개만 연결된
Signal도 발행·목표 개수 산정에서 제외하지 않는다.

사용자가 특정 회사·사업축을 명시하면 `mode=user_scoped`와 선택된
`required_company_axes`만 저장하고, 원문 지시는 `user_directive`에 보존한다. 명시된
기간·지역·출처·탐색 방식·저장 범위는 기본 설정으로 확대하거나 교체하지 않는다.
명시하지 않은 항목에만 기본값을 적용한다. 이 우선순위는 조사 범위 계약이며 Source 원문
확인, 사실·추론 구분, 계보·무결성 검증을 생략하는 권한으로 해석하지 않는다.

`signal_contract.version=1` 이상인 run은 사업축별 active Signal 가운데
`core_market_signal`이 70% 이상이어야 한다. Signal이 3건 이상이면 Claim의 `PRJ-`와
`FAC-` subject를 기준으로 한 프로젝트·설비가 과반을 차지하는지도 감사한다. 이 편중
검사는 일반 시장·정책 subject를 억지로 자산으로 취급하지 않는다.

`signal_contract.version=2`인 완료 run은 감지 활력도 함께 감사한다. 사업축별 Signal이
3건 미만이거나 관찰군·관리군이 각각 20% 미만이거나 경영군이 50%를 넘으면 저강도 사건
누락 또는 고점 승격 편향을 점검한다. 이 비율은 점수 할당량이 아니며 실제 사건이 없을
때는 미달 사유와 다음 재탐색 트리거를 run에 기록한다.

기존 Signal 재평가는 `set-signal-assessment`로 수행하며 이전 평가 Claim을 삭제하지 않고
`superseded` 이력으로 남긴다. 10점 Signal은 `exceptional_score_basis`에 `enterprise_scope`,
`immediate_action`, `delay_loss`, `irreversibility` 네 근거를 모두 저장한다.

`access_attempts`는 접근 방식과 실패 원인을 재현할 수 있을 만큼만 기록한다.
성공한 일반 요청을 모두 기록할 필요는 없지만, 방식 승격·재시도·최종 실패가 발생한
URL은 다음 형태를 권장한다.

```json
{
  "url": "https://example.com/update",
  "attempted_at": "2026-07-25T15:10:00+09:00",
  "method": "browser",
  "outcome": "success",
  "http_status": 200,
  "failure_class": null,
  "retry_count": 1,
  "session_reused": true,
  "final": true,
  "note": "일반 HTTP에서 빈 렌더링 껍데기 확인 후 브라우저로 승격"
}
```

`method`는 `http`, `public_api`, `feed`, `document`, `browser` 중 하나를 우선
사용한다. `failure_class`는 `network`, `rate_limited`, `blocked`,
`javascript_required`, `auth_required`, `content_missing` 중 하나를 사용하고,
성공이면 `null`로 둔다. 민감한 쿠키·토큰·프록시 주소는 run에 저장하지 않는다.
기존 `failed_urls`는 최종 실패 URL의 요약 목록으로 유지한다.

보고서의 Markdown 표현과 HTML 표현은 같은 `wiki_artifacts` row에 함께 저장한다. 보고서의
사실 문장에는 source ID를 붙이고, AI의 경쟁적 시사점은 별도 절로 분리한다. HTML은
단일 파일로 생성하며 Markdown에 실제로 등장한 source ID만 출처 절에 포함한다.
