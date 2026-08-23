"""Use an LLM to re-edit every Signal analysis into an editorial report structure.

The migration is deliberately two-phase: generation writes a reviewable proposal file,
and ``--apply`` atomically updates Insights only after the complete set validates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import market_sensing  # noqa: E402


class EditorialRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_markdown: str
    edit_note: str


class EditorialBatchItem(EditorialRewrite):
    insight_id: str


class EditorialBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EditorialBatchItem]


GENERIC_HEADINGS = {
    "판단 질문과 잠정 결론",
    "판단 제안",
    "확인된 변화 요약",
    "사업 판단 요약",
    "확인된 변화와 시점",
    "일반적 해석과 확인된 차이",
    "통념과 확인된 간극",
    "포스코에 전달되는 사업 영향",
    "포스코홀딩스에 전달되는 사업 영향",
    "포스코인터내셔널에 전달되는 사업 영향",
    "사업 영향 경로",
    "사업 시나리오",
    "조건부 사업 시나리오",
    "조건부 시나리오",
    "지금 확인할 지표",
    "의사결정에 필요한 다음 산출물",
    "결론을 확정·폐기할 조건",
    "판단의 한계",
    "공개 근거 확인",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_analysis(markdown: str) -> str:
    """Drop a generated page replica accidentally embedded in legacy analyses."""
    return re.split(
        r"^##\s+공개 근거 확인\s*$",
        markdown.strip(),
        maxsplit=1,
        flags=re.MULTILINE,
    )[0].strip()


def fenced_blocks(markdown: str) -> set[str]:
    return {
        match.group(0).strip()
        for match in re.finditer(r"```[^\n]*\n.*?```", markdown, flags=re.DOTALL)
    }


def table_blocks(markdown: str) -> set[str]:
    blocks: set[str] = set()
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            index += 1
            continue
        start = index
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            index += 1
        block = "\n".join(lines[start:index]).strip()
        if "| ---" in block or "|---" in block:
            blocks.add(block)
    return blocks


def mask_preserved_blocks(markdown: str) -> tuple[str, dict[str, str]]:
    masked = markdown
    replacements: dict[str, str] = {}
    blocks = list(fenced_blocks(markdown)) + list(table_blocks(markdown))
    blocks.sort(key=lambda value: markdown.find(value))
    for index, block in enumerate(blocks, start=1):
        token = f"[[[PRESERVED_BLOCK_{index:02d}]]]"
        if block not in masked:
            continue
        masked = masked.replace(block, token, 1)
        replacements[token] = block
    return masked, replacements


def restore_preserved_blocks(markdown: str, replacements: dict[str, str]) -> str:
    restored = markdown
    for token, block in replacements.items():
        restored = restored.replace(token, block)
    if "[[[PRESERVED_BLOCK_" in restored:
        raise ValueError("unknown preserved-block token remains in rewrite")
    return restored


def number_tokens(markdown: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z가-힣])\d[\d,.]*(?:%|조원|억원|만\s*톤|톤|GWh|GW|년|월|일)?", markdown))


def url_tokens(markdown: str) -> set[str]:
    return set(re.findall(r"https?://[^\s)>]+", markdown))


def repeated_prose(markdown: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", markdown)
    normalized: list[str] = []
    for paragraph in paragraphs:
        value = paragraph.strip()
        if (
            len(value) < 100
            or value.startswith(("#", "|", "```", "!!!", "???", "- ", "1. "))
        ):
            continue
        normalized.append(re.sub(r"\s+", " ", value))
    return [value for value, count in Counter(normalized).items() if count > 1]


def validate_rewrite(original: str, rewritten: str) -> None:
    market_sensing.validate_signal_analysis(rewritten)
    if fenced_blocks(original) != fenced_blocks(rewritten):
        raise ValueError("fenced code or Mermaid blocks changed")
    if table_blocks(original) != table_blocks(rewritten):
        raise ValueError("a unique Markdown table changed or disappeared")
    if number_tokens(original) != number_tokens(rewritten):
        missing = sorted(number_tokens(original) - number_tokens(rewritten))
        added = sorted(number_tokens(rewritten) - number_tokens(original))
        raise ValueError(f"numeric tokens changed; missing={missing}, added={added}")
    if url_tokens(original) != url_tokens(rewritten):
        raise ValueError("URLs changed")
    if repeated_prose(rewritten):
        raise ValueError("the rewrite still contains repeated prose paragraphs")
    h2_headings = re.findall(r"^##\s+(.+)$", rewritten, flags=re.MULTILINE)
    h3_headings = re.findall(r"^###\s+(.+)$", rewritten, flags=re.MULTILINE)
    if not 3 <= len(h2_headings) <= 5:
        raise ValueError("report must use three to five H2 chapters")
    if len(h3_headings) < 5:
        raise ValueError("report must use H3 subsections beneath its H2 chapters")
    if re.search(r"^#\s+", rewritten, flags=re.MULTILINE):
        raise ValueError("analysis Markdown must not repeat the structured H1 title")
    headings = h2_headings
    if any(heading in GENERIC_HEADINGS for heading in headings):
        raise ValueError("generic schema heading remains")


INSTRUCTIONS = """당신은 현재 MyPIN 보고서 화면에 게재할 포스코그룹 임직원용 고급 산업 보고서의 편집자다.
입력은 이미 검증된 마켓 시그널 상세분석이다. 사실 조사나 새 분석이 아니라 편집만 한다.

필수 규칙:
1. H1은 쓰지 않는다. 구조화된 Signal 제목이 화면 H1이다. 본문은 H2를 정확히 3~5개 사용하고,
   각 H2 아래에 실제로 종속되는 H3를 둔다. H4는 반증 조건·담당·감지 조건처럼 H3보다
   한 단계 더 좁은 항목에만 선택적으로 사용한다. 제목 레벨을 건너뛰지 않는다.
2. H2는 각 문서의 구체적 결론·긴장·판단 기준을 드러내는 고유한 명사구로 새로 쓴다.
3. '확인된 변화 요약', '사업 판단 요약', '확인된 변화와 시점', '사업 영향 경로',
   '사업 시나리오', '지금 확인할 지표', '의사결정에 필요한 다음 산출물',
   '결론을 확정·폐기할 조건', '판단의 한계', '공개 근거 확인'을 H2로 쓰지 않는다.
4. 판단 질문과 잠정 결론은 첫 H2 아래의 서로 구분되는 H3에 배치하고 각각
   **판단 질문:**, **잠정 결론:** 라벨도 보존한다.
5. 확인 사실을 설명하는 문단 앞에는 **확인된 변화:**, 회사로 전달되는 경로 앞에는
   **사업 영향:** 라벨을 정확히 한 번씩 둔다.
6. 시나리오 표 앞에는 **조건부 시나리오:** 라벨을 둔다. 표 내용은 한 글자도 바꾸지 않는다.
7. 관찰 목록 앞에는 **이번 주 확인할 지표:**, 번호 목록 앞에는 **다음 산출물:** 라벨을 둔다.
8. **반증 조건:**, **확인 담당:**, **감지 트리거:**를 각각 명시한다. 반증 조건은
   결론을 확정하거나 폐기할 한 가지 확인, 담당은 실제 확인할 직무·조직 역할,
   감지 트리거는 관찰값이 어떤 상태가 되면 재판단할지를 쓴다.
   판단의 한계 admonition도 보존한다.
9. 모든 근거 수치·공개 날짜·고유명사·인용 취지·표·Mermaid·링크는 그대로 보존한다.
   새 사실, 새 수치, 새 시한, 새 인과관계를 만들지 않는다. 공개 근거가 없는 내부
   월말·분기말·임의 산출물 날짜는 쓰지 않는다.
10. 중복된 요약, 두 번째 보고서, 반복 문단은 한 번만 남긴다. Source/Claim 추적용 메타나
   페이지 자체의 '왜 중요한가/판단 근거/출처' 복제본은 상세분석에서 제거한다.
11. 내용 순서는 독자가 판단하기 좋은 흐름으로 재배열할 수 있지만, 의미를 축약해 버리지 않는다.
12. 본문은 존댓말, H2는 존댓말 종결이 아닌 결론형 명사구로 쓴다.
13. 출력 Markdown은 MyPIN이 semantic HTML과 중첩 목차로 직접 렌더링한다. 장 제목과
   하위 제목의 포함 관계가 본문 의미와 일치해야 하며, 목차용 빈 제목을 만들지 않는다.
14. 출력은 analysis_markdown과 짧은 edit_note만 반환한다.
"""


def selected_insights(
    wiki_root: Path, signal_ids: list[str]
) -> list[tuple[Path, dict[str, Any]]]:
    insights = {
        str(record.get("insight_id")): (path, record)
        for path, record in market_sensing.insight_records(wiki_root)
    }
    if not signal_ids:
        return sorted(insights.values(), key=lambda item: item[0].name)
    wanted: list[tuple[Path, dict[str, Any]]] = []
    signals = {
        str(record.get("signal_id")): record
        for _, record in market_sensing.signal_records(wiki_root)
    }
    missing = sorted(set(signal_ids) - set(signals))
    if missing:
        raise ValueError("unknown Signal IDs: " + ", ".join(missing))
    for signal_id in signal_ids:
        insight_id = str(signals[signal_id].get("insight_id") or "")
        if insight_id not in insights:
            raise ValueError(f"Signal has no Insight record: {signal_id}")
        wanted.append(insights[insight_id])
    return wanted


def generate_one(
    client: Any,
    model: str,
    insight: dict[str, Any],
    previous_error: str = "",
) -> EditorialRewrite:
    original = str(insight.get("analysis_markdown") or "").strip()
    prompt = (
        f"Signal 제목: {insight.get('title') or '-'}\n"
        f"문단 Insight: {insight.get('summary') or '-'}\n\n"
        "편집할 상세분석 원문:\n<<<MARKDOWN\n"
        + original
        + "\nMARKDOWN>>>"
    )
    if previous_error:
        prompt += f"\n\n직전 출력의 검증 오류: {previous_error}\n오류를 고쳐 다시 작성하라."
    response = client.responses.parse(
        model=model,
        instructions=INSTRUCTIONS,
        input=prompt,
        text_format=EditorialRewrite,
        reasoning={"effort": "medium"},
        max_output_tokens=16000,
        store=False,
    )
    if response.output_parsed is None:
        raise RuntimeError("model returned no parsed editorial rewrite")
    return response.output_parsed


def generate_proposals(
    wiki_root: Path, output: Path, model: str, signal_ids: list[str]
) -> list[dict[str, Any]]:
    from openai import OpenAI

    client = OpenAI()
    proposals: list[dict[str, Any]] = []
    insights = selected_insights(wiki_root, signal_ids)
    for index, (path, insight) in enumerate(insights, start=1):
        original = str(insight.get("analysis_markdown") or "").strip()
        error = ""
        for attempt in range(1, 4):
            try:
                result = generate_one(client, model, insight, error)
                rewritten = result.analysis_markdown.strip()
                validate_rewrite(canonical_analysis(original), rewritten)
                proposals.append(
                    {
                        "insight_id": insight.get("insight_id"),
                        "path": str(path.relative_to(wiki_root)),
                        "source_sha256": sha256_text(original),
                        "analysis_markdown": rewritten,
                        "edit_note": result.edit_note,
                    }
                )
                market_sensing.atomic_write_text(
                    output,
                    json.dumps({"model": model, "items": proposals}, ensure_ascii=False, indent=2)
                    + "\n",
                )
                print(f"[{index}/{len(insights)}] {path.stem}: ok", flush=True)
                break
            except Exception as exc:
                error = str(exc)
                print(
                    f"[{index}/{len(insights)}] {path.stem}: attempt {attempt} failed: {error}",
                    flush=True,
                )
                if attempt == 3:
                    raise
    headings = [
        heading
        for item in proposals
        for heading in re.findall(
            r"^##\s+(.+)$", item["analysis_markdown"], flags=re.MULTILINE
        )
    ]
    duplicates = sorted(heading for heading, count in Counter(headings).items() if count > 1)
    if duplicates:
        raise ValueError("LLM reused editorial H2 headings across reports: " + ", ".join(duplicates))
    return proposals


def generate_codex_batch(
    batch: list[tuple[Path, dict[str, Any]]],
    model: str,
    workspace: Path,
    scratch: Path,
    retry_note: str = "",
) -> EditorialBatch:
    replacement_maps: dict[str, dict[str, str]] = {}
    payload: list[dict[str, Any]] = []
    for path, insight in batch:
        insight_id = str(insight.get("insight_id") or path.stem)
        masked, replacements = mask_preserved_blocks(
            canonical_analysis(str(insight.get("analysis_markdown") or ""))
        )
        replacement_maps[insight_id] = replacements
        payload.append(
            {
                "insight_id": insight_id,
                "title": insight.get("title"),
                "summary": insight.get("summary"),
                "analysis_markdown": masked,
            }
        )
    prompt = (
        INSTRUCTIONS
        + "\n아래 JSON 배열의 모든 문서를 편집하라. 각 insight_id를 그대로 돌려주고 "
        "입력 순서를 유지하라. 파일을 읽거나 수정하지 말고 제공된 텍스트만 편집하라. "
        "[[[PRESERVED_BLOCK_00]]] 형식의 잠금 토큰은 표·도식 자리이므로 철자와 위치를 "
        "바꾸지 말고 필요한 블록마다 정확히 한 번 보존하라.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    if retry_note:
        prompt += (
            "\n\n직전 출력은 다음 검증 오류로 거부됐다: "
            + retry_note
            + "\n오류가 난 항목만 다시 쓰되 원문의 표와 fenced block은 byte-for-byte 그대로 복사하라."
        )
    schema_path = scratch / "codex-output-schema.json"
    output_path = scratch / "codex-last-message.json"
    market_sensing.atomic_write_text(
        schema_path,
        json.dumps(EditorialBatch.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
    )
    environment = dict(os.environ)
    environment.pop("OPENAI_API_KEY", None)
    desktop_codex = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "OpenAI"
        / "Codex"
        / "bin"
        / "codex.exe"
    )
    node_executable = Path(r"C:\Program Files\nodejs\node.exe")
    codex_script = (
        Path(os.environ.get("APPDATA", ""))
        / "npm"
        / "node_modules"
        / "@openai"
        / "codex"
        / "bin"
        / "codex.js"
    )
    if desktop_codex.is_file():
        executable = [str(desktop_codex)]
    elif codex_script.is_file() and node_executable.is_file():
        executable = [str(node_executable), str(codex_script)]
    else:
        raise RuntimeError("Codex CLI executable was not found")
    command = [
        *executable,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "-c",
        'model_reasoning_effort="high"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "--color",
        "never",
        "--cd",
        str(workspace),
        "-",
    ]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        capture_output=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Codex editorial generation failed: "
            + (completed.stderr or completed.stdout)[-3000:]
        )
    parsed = EditorialBatch.model_validate_json(output_path.read_text(encoding="utf-8"))
    for item in parsed.items:
        item.analysis_markdown = restore_preserved_blocks(
            item.analysis_markdown, replacement_maps.get(item.insight_id, {})
        )
    return parsed


def generate_proposals_with_codex(
    wiki_root: Path, output: Path, model: str, batch_size: int, signal_ids: list[str]
) -> list[dict[str, Any]]:
    insights = selected_insights(wiki_root, signal_ids)
    proposals: list[dict[str, Any]] = []
    if output.is_file():
        saved = json.loads(output.read_text(encoding="utf-8"))
        proposals = list(saved.get("items") or [])
    saved_by_id = {str(item.get("insight_id")): item for item in proposals}
    remaining: list[tuple[Path, dict[str, Any]]] = []
    for path, insight in insights:
        insight_id = str(insight.get("insight_id"))
        original = str(insight.get("analysis_markdown") or "").strip()
        saved = saved_by_id.get(insight_id)
        if saved and saved.get("source_sha256") == sha256_text(original):
            validate_rewrite(
                canonical_analysis(original), str(saved.get("analysis_markdown") or "")
            )
            continue
        remaining.append((path, insight))
    scratch = output.parent
    for start in range(0, len(remaining), batch_size):
        batch = remaining[start : start + batch_size]
        generated = generate_codex_batch(batch, model, PROJECT_ROOT, scratch)
        expected = [str(insight.get("insight_id")) for _, insight in batch]
        actual = [item.insight_id for item in generated.items]
        if actual != expected:
            raise ValueError(f"Codex returned the wrong Insight sequence: {actual} != {expected}")
        for (path, insight), result in zip(batch, generated.items, strict=True):
            original = str(insight.get("analysis_markdown") or "").strip()
            rewritten = result.analysis_markdown.strip()
            try:
                validate_rewrite(canonical_analysis(original), rewritten)
            except ValueError as exc:
                print(f"{path.stem}: batch validation failed, retrying alone: {exc}", flush=True)
                error = str(exc)
                for attempt in range(1, 3):
                    retry = generate_codex_batch(
                        [(path, insight)], model, PROJECT_ROOT, scratch, error
                    ).items[0]
                    rewritten = retry.analysis_markdown.strip()
                    try:
                        validate_rewrite(canonical_analysis(original), rewritten)
                        result = retry
                        break
                    except ValueError as retry_exc:
                        error = str(retry_exc)
                        if attempt == 2:
                            raise
            proposals.append(
                {
                    "insight_id": insight.get("insight_id"),
                    "path": str(path.relative_to(wiki_root)),
                    "source_sha256": sha256_text(original),
                    "analysis_markdown": rewritten,
                    "edit_note": result.edit_note,
                }
            )
        market_sensing.atomic_write_text(
            output,
            json.dumps({"model": model, "items": proposals}, ensure_ascii=False, indent=2)
            + "\n",
        )
        print(
            f"[{len(proposals)}/{len(insights)}] Codex editorial batch: ok",
            flush=True,
        )
    headings = [
        heading
        for item in proposals
        for heading in re.findall(
            r"^##\s+(.+)$", item["analysis_markdown"], flags=re.MULTILINE
        )
    ]
    duplicates = sorted(heading for heading, count in Counter(headings).items() if count > 1)
    if duplicates:
        raise ValueError("LLM reused editorial H2 headings across reports: " + ", ".join(duplicates))
    return proposals


def apply_proposals(
    wiki_root: Path, proposal_path: Path, backup_path: Path, signal_ids: list[str]
) -> int:
    payload = json.loads(proposal_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    current = {
        str(record.get("insight_id")): (path, record)
        for path, record in selected_insights(wiki_root, signal_ids)
    }
    proposed_ids = {str(item.get("insight_id")) for item in items}
    if proposed_ids != set(current):
        raise ValueError("proposal must cover the complete current Insight set")
    backups: list[dict[str, Any]] = []
    updates: list[tuple[Path, dict[str, Any]]] = []
    for item in items:
        insight_id = str(item["insight_id"])
        path, record = current[insight_id]
        original = str(record.get("analysis_markdown") or "").strip()
        if sha256_text(original) != item["source_sha256"]:
            raise ValueError(f"Insight changed after generation: {insight_id}")
        rewritten = str(item["analysis_markdown"]).strip()
        validate_rewrite(canonical_analysis(original), rewritten)
        backups.append({"path": str(path.relative_to(wiki_root)), "record": record})
        updated = dict(record)
        updated["analysis_markdown"] = rewritten
        updated["updated_at"] = market_sensing.timestamp()
        updates.append((path, updated))
    market_sensing.atomic_write_text(
        backup_path,
        json.dumps(backups, ensure_ascii=False, indent=2) + "\n",
    )
    for path, record in updates:
        market_sensing.write_json(path, record)
    return len(updates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wiki-root", type=Path, default=PROJECT_ROOT / "market-sensing-wiki")
    parser.add_argument(
        "--proposals",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "signal-report-editorial" / "proposals.json",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=PROJECT_ROOT / "tmp" / "signal-report-editorial" / "before.json",
    )
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--provider", choices=("codex", "api"), default="codex")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--signal-id", action="append", default=[])
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    args.proposals.parent.mkdir(parents=True, exist_ok=True)
    if args.generate:
        if args.provider == "codex":
            generate_proposals_with_codex(
                args.wiki_root, args.proposals, args.model, args.batch_size
                , args.signal_id
            )
        else:
            generate_proposals(args.wiki_root, args.proposals, args.model, args.signal_id)
    if args.apply:
        count = apply_proposals(
            args.wiki_root, args.proposals, args.backup, args.signal_id
        )
        print(json.dumps({"action": "applied", "insights": count}, ensure_ascii=False))
    if not args.generate and not args.apply:
        parser.error("choose --generate and/or --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
