from __future__ import annotations

import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cli_tools import ALL_COMMANDS, READ_ONLY_COMMANDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import market_sensing  # noqa: E402


MAINTENANCE_COMMANDS = {
    "migrate-analytics-contract",
    "migrate-signal-scores",
    "migrate-to-sqlite",
    "prune-to-signals",
}
MAX_ARGUMENTS = 160


@dataclass(frozen=True, slots=True)
class OperationRequest:
    command: str
    arguments: tuple[str, ...]
    input_files: dict[str, str | bytes]
    confirm: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperationRequest:
        command = str(data.get("command") or "").strip()
        if command not in ALL_COMMANDS:
            raise ValueError(f"지원하지 않는 작업입니다: {command}")
        raw_arguments = data.get("arguments", [])
        if not isinstance(raw_arguments, list) or len(raw_arguments) > MAX_ARGUMENTS:
            raise ValueError(f"arguments는 최대 {MAX_ARGUMENTS}개의 문자열 배열이어야 합니다.")
        arguments = tuple(str(item) for item in raw_arguments)
        if any("\x00" in item or len(item) > 10_000 for item in arguments):
            raise ValueError("작업 인자가 올바르지 않습니다.")
        if "--backup-path" in arguments or "--output" in arguments:
            raise ValueError("backup/output 경로는 API 서버가 관리합니다.")

        confirm = str(data.get("confirm") or "").strip() or None
        required_confirmation = _required_confirmation(command, arguments)
        if required_confirmation and confirm != required_confirmation:
            raise ValueError(
                f"이 작업은 confirm='{required_confirmation}' 확인값이 필요합니다."
            )
        return cls(
            command=command,
            arguments=arguments,
            input_files=_decode_input_files(data.get("input_files", {})),
            confirm=confirm,
        )


def _required_confirmation(command: str, arguments: tuple[str, ...]) -> str | None:
    if command in MAINTENANCE_COMMANDS:
        if command == "prune-to-signals" and "--dry-run" in arguments:
            return None
        return command
    if command == "add-source" and "--force" in arguments:
        return "add-source:force"
    return None


def _decode_input_files(value: object) -> dict[str, str | bytes]:
    if not isinstance(value, dict):
        raise ValueError("input_files는 파일명별 내용 객체여야 합니다.")
    decoded: dict[str, str | bytes] = {}
    for name, item in value.items():
        filename = str(name)
        if isinstance(item, str):
            decoded[filename] = item
            continue
        if not isinstance(item, dict):
            raise ValueError(f"input_files.{filename} 내용이 올바르지 않습니다.")
        encoding = str(item.get("encoding") or "utf-8").lower()
        content = item.get("content")
        if not isinstance(content, str):
            raise ValueError(f"input_files.{filename}.content는 문자열이어야 합니다.")
        if encoding == "utf-8":
            decoded[filename] = content
        elif encoding == "base64":
            try:
                decoded[filename] = base64.b64decode(content, validate=True)
            except ValueError as exc:
                raise ValueError(f"input_files.{filename} base64가 올바르지 않습니다.") from exc
        else:
            raise ValueError("input_files encoding은 utf-8 또는 base64만 지원합니다.")
    return decoded


def operation_catalog() -> dict[str, Any]:
    parser = market_sensing.build_parser()
    subparsers_action = next(
        action for action in parser._actions if hasattr(action, "choices") and action.dest == "command"
    )
    command_help = {
        action.dest: action.help for action in subparsers_action._choices_actions
    }
    operations = []
    for command in sorted(ALL_COMMANDS):
        if command in READ_ONLY_COMMANDS:
            mode = "read"
        elif command in MAINTENANCE_COMMANDS:
            mode = "maintenance"
        else:
            mode = "write"
        operations.append(
            {
                "command": command,
                "mode": mode,
                "confirmation_required": command in MAINTENANCE_COMMANDS,
                "description": command_help.get(command),
                "parameters": _parameter_schema(subparsers_action.choices[command]),
            }
        )
    return {
        "operations": operations,
        "count": len(operations),
        "input_file_encodings": ["utf-8", "base64"],
        "server_managed_paths": ["backup", "output"],
    }


def _parameter_schema(parser: Any) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for action in parser._actions:
        if action.dest in {"help", "root", "func"}:
            continue
        choices = action.choices
        if choices is not None:
            choices = list(choices)
        parameters.append(
            {
                "flags": list(action.option_strings),
                "name": action.dest,
                "required": bool(getattr(action, "required", False)),
                "repeatable": action.__class__.__name__ == "_AppendAction",
                "boolean": action.__class__.__name__ in {"_StoreTrueAction", "_StoreFalseAction"},
                "choices": choices,
                "input_file": any(
                    flag
                    in {
                        "--analysis-file",
                        "--content-file",
                        "--coverage-file",
                        "--decision-file",
                        "--estimate-file",
                        "--image-file",
                        "--impact-estimate-file",
                        "--input",
                        "--mapping-file",
                        "--quantification-decision-file",
                        "--spec-file",
                        "--structured-analysis-file",
                    }
                    for flag in action.option_strings
                ),
                "description": action.help,
            }
        )
    return parameters


def parse_cli_result(result: dict[str, object]) -> dict[str, object]:
    stdout = str(result.get("stdout") or "").strip()
    if stdout:
        try:
            result = {**result, "data": json.loads(stdout)}
        except json.JSONDecodeError:
            pass
    return result
