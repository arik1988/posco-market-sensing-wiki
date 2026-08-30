# Market Sensing Intelligence

`WIKI-SETTINGS.md`에 설정된 포스코 패밀리 우선 기업의 외부 변화를
Source → Claim → Signal → Insight로 연결하는 로컬 조사 도구입니다.

## 저장 원칙

프로그램이 만드는 모든 데이터는 `market-sensing-wiki/data/market_sensing.db` 한 파일에 저장합니다.

- Source 메타데이터와 수집 원문 BLOB
- Claim, Signal, Insight, 전략 추세·가정·경보
- 검토 대기·해결 이력과 조사 Run
- 이미지 BLOB, 감사 결과, 브리프 Markdown/HTML, 작업 로그
- `WIKI-SETTINGS.md`에서 파싱한 설정 캐시

Signal별 `.md`, Claim별 `.json`, `.system/raw/` 원문 파일은 만들지 않습니다. Insight의
`payload_json`에는 UI용 `analysis_structured` JSON과 읽기용 `analysis_markdown`을 함께
보관합니다. 보고서 Markdown/HTML도 SQLite artifact의 TEXT 값입니다. 코드, 테스트,
운영 문서, `WIKI-SETTINGS.md`는 데이터 산물이 아니므로 저장소 파일로 유지합니다.

기본 DB 위치를 바꾸려면 실행 전에 환경변수를 지정합니다.

```powershell
$env:MYPIN_DATABASE_PATH = "D:\MyPIN\market_sensing.db"
```

이 변수는 수집 도구의 DB 위치를 바꿉니다. MyPIN importer도 이 SQLite snapshot을 직접
읽을 수 있지만, 기존 MyPIN 계정·대화 데이터가 든 DB와 물리적으로 합칠 때는 먼저 전체
application DB를 backup·이관해야 합니다. 경로만 바꿔 기존 사용자 데이터를 버리면 안
됩니다. 별도 전송본이 필요할 때는 실행 중인 DB 파일을 복사하지 말고 SQLite online
backup을 사용해야 합니다.

## 시작

```powershell
python skills/market-sensing-intelligence/scripts/market_sensing.py scaffold market-sensing-wiki
```

기존 파일 저장소는 다음 명령으로 해시와 외래키를 검증한 뒤 이관합니다.

```powershell
python skills/market-sensing-intelligence/scripts/market_sensing.py migrate-to-sqlite market-sensing-wiki
python skills/market-sensing-intelligence/scripts/market_sensing.py migrate-to-sqlite market-sensing-wiki --remove-legacy-files
```

두 번째 명령은 DB `integrity_check`와 원문 해시 검증이 성공한 경우에만 기존 데이터 파일과 생성 Markdown을 제거합니다. 기존 DB가 있으면 먼저 `data/backups/`에 online backup을 만듭니다.

### MkDocs AI 조사 탭

`wiki_run.bat`를 실행하면 MkDocs와 로컬 Deep Agent API가 함께 시작됩니다. 상단의
`AI 조사` 탭에서 조사 주제, 회사·사업축, 기간, provider를 선택해 즉시 실행하거나
매일·매주·매월 반복 일정을 저장할 수 있습니다. 일정은 Asia/Seoul 기준 시각과 매번
다시 확인할 최근 일수를 가지며, 화면에서 일시정지·재개·삭제할 수 있습니다.

- `P-GPT`: 실제 운영. `PGPT_API_KEY`, `PGPT_EMPLOYEE_NO`, `PGPT_MODEL`을 설정합니다.
  기본 endpoint는 `http://pgpt.posco.com/s0la01-gpt/v1`이며 승인 host 외에는 자격증명을
  보내지 않습니다.
- `Codex OAuth`: 개발 단계. 별도 API 키 대신 로컬 `codex login`의 ChatGPT OAuth를
  사용합니다.
- 검색은 두 provider 모두 DuckDuckGo Lite를 사용합니다. Codex의 내장 웹 검색이나
  셸·파일 도구에는 의존하지 않습니다.
- `SQLite에 완전 발행`은 기본으로 켜져 있습니다. 끄면 SQLite 저장 명령이 차단된 읽기
  전용 초안 모드가 됩니다.
- 조사 서버 연결이 끊겨도 범위 설정 UI는 계속 보이며, 실행·일정 저장이 불가능한 이유를
  상태 영역에서 확인할 수 있습니다. 반복 일정은 조사 서버가 실행 중일 때 기존 직렬
  실행 큐에 들어갑니다.

처음 실행하면 프로젝트 로컬 `.venv-agent`를 만들고
`tools/project/requirements-agent.txt`를 설치합니다. 조사 API는 브라우저가 있는 PC의
`127.0.0.1:8201`에서만 열리므로 LAN에서 MkDocs를 읽는 사용자는 조사 실행 기능을 사용할
수 없습니다.

### 외부 프로그램 제어 API

같은 PC의 다른 프로그램은 `wiki_run.bat`가 시작한 `http://127.0.0.1:8201` API로
관심 범위와 운영 설정을 관리하고, 조사·발행·감사 작업을 실행하거나 완전한 SQLite
스냅샷을 받을 수 있습니다. 서버는 loopback에만 바인딩되며 셸 명령·작업 디렉터리·임의
파일 경로는 받지 않습니다.

```text
GET  /api/capabilities
GET  /api/settings
PATCH /api/settings
GET|POST|PUT|DELETE /api/settings/company-axes
POST /api/research/runs
GET  /api/research/runs/{run_id}
GET|POST|PUT|DELETE /api/research/schedules[/schedule_id]
GET  /api/operations
POST /api/operations
GET  /api/operations/{operation_id}
GET  /api/database/snapshot
GET|PUT|DELETE /api/signal-favorites[/signal_id]
GET|POST /api/signal-comments
GET|DELETE /api/signal-comments/{comment_id}
```

`GET /api/operations`는 지원하는 모든 공용 Market Sensing 명령과 인자·선택값·임시 파일
필드를 기계 판독 가능한 catalog로 반환합니다. `POST /api/operations`는 catalog에 있는
명령만 기존 CLI 검증기로 실행하고 `operation_id`를 반환합니다. 모든 DB 쓰기는 조사와
같은 직렬 큐를 사용합니다. 입력 파일은 `input_files`의 UTF-8 또는 base64 내용만 허용하고
완료 뒤 삭제합니다. 마이그레이션과 실제 prune은 명령명과 동일한 `confirm` 값이 있어야
하며 prune 백업 경로는 서버가 자동 생성합니다.

```json
{
  "command": "audit",
  "arguments": ["--stale-days", "180"],
  "input_files": {}
}
```

관심 회사·사업축은 다음처럼 등록합니다. `POST`는 추가, `PUT`은 전체 교체, `DELETE`는
지정 조합 삭제입니다. 마지막 조합은 삭제할 수 없습니다. 변경 결과는
`WIKI-SETTINGS.md`와 SQLite `watchlist` 캐시에 한 번에 동기화됩니다.

```json
{
  "company_axes": [
    {"company": "POSCO Holdings", "business_axis": "리튬"},
    {"company": "POSCO Holdings", "business_axis": "전략광물"}
  ]
}
```

`PATCH /api/settings`로 기술·프로젝트·국가·출처 우선순위·리스크 신호·보고서 중점과 운영
값도 부분 갱신할 수 있습니다. 조사 요청에 `company_axes`를 생략하면 등록된 관심 범위를
기본값으로 사용합니다.

브라우저 기반의 다른 로컬 프로그램이 호출할 때는 허용 origin을 쉼표로 등록한 뒤 서버를
시작합니다. 네이티브 프로그램·백엔드 호출에는 CORS 설정이 필요하지 않습니다.

```powershell
$env:MARKET_API_ALLOWED_ORIGINS = "http://127.0.0.1:8000,http://localhost:8100"
```

조사 요청 예시는 다음과 같습니다. `publish`가 `true`이면 기존 Source → Claim → Signal →
Insight 발행 계약을 따르며, 작업은 SQLite 경쟁 쓰기를 막기 위해 직렬 실행됩니다.

```json
{
  "topic": "철강 수입규제 변화",
  "topic_company": "POSCO",
  "company_axes": [{"company": "POSCO", "business_axis": "철강"}],
  "date_from": "2026-08-01",
  "date_to": "2026-08-30",
  "provider": "codex",
  "codex_model": "gpt-5.6-luna",
  "codex_effort": "medium",
  "publish": true
}
```

`POST /api/research/runs`는 `202 Accepted`와 `run_id`를 반환합니다. 완료 여부는 해당
`run_id`로 조회합니다. `GET /api/database/snapshot`은 실행 중인 원본 DB 파일을 직접
복사하지 않고 SQLite online backup으로 만든 일관된 `.db` 파일을 반환합니다. 응답의
`X-Snapshot-SHA256`과 `X-Snapshot-Generated-At` 헤더로 파일 무결성과 생성 시각을
확인할 수 있습니다.

## 동작 흐름

```text
공개 원문 확인
  → Source 메타데이터 + 원문 BLOB 저장
  → 원자 Claim 저장·충돌 검토
  → Signal + Insight + analysis_structured JSON + analysis_markdown 산문 저장
  → 감사·검색·trace가 SQLite를 직접 조회
  → MyPIN SQLite importer가 snapshot을 읽어 목록·상세·근거 계보로 반영
```

입력용 `--content-file`, `--analysis-file`, `--structured-analysis-file`,
`--estimate-file`은 명령 실행 시 읽는 임시 입력입니다. 등록 이후 정본은 SQLite이며 입력
파일 경로에 의존하지 않습니다.

## 주요 명령

```powershell
# 설정 반영
python skills/market-sensing-intelligence/scripts/market_sensing.py sync-settings market-sensing-wiki

# 저장 지식 검색
python skills/market-sensing-intelligence/scripts/market_sensing.py search market-sensing-wiki --query "LFP 수산화리튬" --limit 10

# Signal부터 원문까지 추적
python skills/market-sensing-intelligence/scripts/market_sensing.py trace-signal market-sensing-wiki --signal-id SIG-... --depth 4

# 전체 무결성 감사 — 결과도 SQLite artifact로 저장
python skills/market-sensing-intelligence/scripts/market_sensing.py audit market-sensing-wiki

# 변경 브리프 — Markdown/HTML 문자열 모두 SQLite artifact로 저장
python skills/market-sensing-intelligence/scripts/market_sensing.py brief market-sensing-wiki --since 2026-08-22 --html
```

`sync-obsidian`은 이전 자동화 호환을 위해 남아 있지만 파일을 생성하지 않습니다. 호출하면 SQLite가 정본임을 확인하고 종료합니다.

## SQLite 테이블 경계

| 테이블 | 저장 내용 |
|---|---|
| `wiki_records` | Source·Claim·Signal·Insight·Run·Review 등 버전 가능한 JSON payload |
| `wiki_source_contents` | 수집 원문 BLOB과 raw/normalized SHA-256 |
| `wiki_binary_assets` | 권리 확인 이미지와 해시 |
| `wiki_artifacts` | 감사·브리프·보고서·이벤트의 Markdown/HTML TEXT |
| `wiki_settings` | `WIKI-SETTINGS.md` 파싱 결과 |
| `wiki_operation_log` | 모든 저장 작업 이력 |
| `wiki_schema_migrations` | DB 스키마 버전 |
| `wiki_signal_favorites` | 불투명 사용자 키별 Signal 좋아요와 등록 시각 |
| `wiki_research_schedules` | 즉시 실행과 같은 범위를 재사용하는 반복 조사 일정 |

레코드 payload는 기존 데이터 계약을 보존하고, 저장 위치만 파일에서 SQLite로 바뀝니다. Source 원문은 불변이며 수정은 새 Source revision으로 남기고, Claim의 대체·충돌·취소 이력도 삭제하지 않습니다.

## Signal 좋아요 API

이 PC의 MyPIN UI와 별개로, API 서버는 사용자별 Signal 좋아요 저장 계약을 제공합니다.
인증 계층에서 파생한 128자 이하의 불투명 키를 `X-Mypin-User-Key` 헤더로 전달합니다.
이름·사번·이메일을 직접 보내거나 저장하지 마세요.

| 메서드 | 경로 | 결과 |
|---|---|---|
| `GET` | `/api/signal-favorites` | 좋아요 Signal ID와 등록 시각 최신순 목록 |
| `GET` | `/api/signal-favorites/{signal_id}` | 단건 좋아요 여부 |
| `PUT` | `/api/signal-favorites/{signal_id}` | 좋아요 등록, 신규는 `201`, 기존은 `200` |
| `DELETE` | `/api/signal-favorites/{signal_id}` | 좋아요 해제, 반복 호출 가능 |

`PUT`과 `DELETE`는 멱등이며 존재하지 않는 Signal은 `404 signal_not_found`를 반환합니다.
운영 사내 시스템에서는 인증 게이트웨이가 사용자 키 헤더를 주입하고 클라이언트의 임의
헤더 위조를 차단해야 합니다. 좋아요는 Signal 본문과 분리된
`wiki_signal_favorites(user_key, signal_id, favorited_at)`에 저장되므로 Signal 재평가나
Insight 갱신으로 덮어쓰지 않습니다.

## 검증

```powershell
python -m unittest tests.test_sqlite_market_sensing -v
python -m unittest tests.test_signal_favorites_api -v
python -m unittest discover -s tests
git diff --check
```

핵심 검증 항목은 `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, 레코드 종류별 건수, Source 원문 BLOB 수·해시, 검색·감사·trace의 파일 비의존성, Windows에서 연결 종료 후 DB 이동·백업 가능 여부입니다.

## 프로젝트 파일

| 경로 | 역할 |
|---|---|
| `AGENTS.md` | 조사·발행·검증 규칙 |
| `WIKI-SETTINGS.md` | 사람이 편집하는 조사 범위와 평가 기준 |
| `skills/market-sensing-intelligence/` | 데이터 계약과 CLI 구현 |
| `market-sensing-wiki/data/market_sensing.db` | 프로그램 데이터의 단일 정본 |
| `tests/test_sqlite_market_sensing.py` | SQLite 저장·조회·무결성 회귀 테스트 |

`.examples/`는 읽기 전용 참고 구현입니다.
