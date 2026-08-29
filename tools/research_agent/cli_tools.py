from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path


_READ_ONLY_COMMANDS = {"audit", "search", "show-settings", "trace-signal"}
_PUBLISH_COMMANDS = _READ_ONLY_COMMANDS | {
    "add-source",
    "add-claim",
    "add-signal",
    "scout",
    "set-impact-estimate",
}
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FILE_OPTIONS = {
    "--analysis-file",
    "--content-file",
    "--estimate-file",
    "--structured-analysis-file",
}


class MarketSensingCli:
    def __init__(self, project_root: Path, *, publish: bool) -> None:
        self.project_root = project_root.resolve()
        self.publish = publish
        self.script = (
            self.project_root
            / "skills"
            / "market-sensing-intelligence"
            / "scripts"
            / "market_sensing.py"
        )

    async def run(
        self,
        command: str,
        arguments: list[str] | None = None,
        input_files: dict[str, str] | None = None,
    ) -> dict[str, object]:
        allowed = _PUBLISH_COMMANDS if self.publish else _READ_ONLY_COMMANDS
        if command not in allowed:
            return {"ok": False, "error": f"허용되지 않은 명령입니다: {command}"}
        raw_args = list(arguments or [])
        if any("\x00" in arg or len(arg) > 10_000 for arg in raw_args):
            return {"ok": False, "error": "명령 인자가 올바르지 않습니다."}
        files = input_files or {}
        if len(files) > 8 or sum(len(value) for value in files.values()) > 800_000:
            return {"ok": False, "error": "임시 입력 파일 한도를 초과했습니다."}
        with tempfile.TemporaryDirectory(prefix="market-agent-input-") as temp:
            temp_root = Path(temp)
            mapped: dict[str, Path] = {}
            for name, content in files.items():
                if not _SAFE_FILE_NAME.fullmatch(name):
                    return {
                        "ok": False,
                        "error": f"잘못된 임시 파일 이름입니다: {name}",
                    }
                path = temp_root / name
                path.write_text(content, encoding="utf-8")
                mapped[name] = path
            for index, arg in enumerate(raw_args):
                if arg.startswith("@") and arg[1:] not in mapped:
                    return {"ok": False, "error": "등록되지 않은 임시 파일입니다."}
                if arg in _FILE_OPTIONS:
                    if index + 1 >= len(raw_args) or not raw_args[index + 1].startswith(
                        "@"
                    ):
                        return {
                            "ok": False,
                            "error": f"{arg}에는 input_files의 @파일명만 사용할 수 있습니다.",
                        }
            args = [
                str(mapped[arg[1:]])
                if arg.startswith("@") and arg[1:] in mapped
                else arg
                for arg in raw_args
            ]
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(self.script),
                command,
                str(self.project_root / "market-sensing-wiki"),
                *args,
                cwd=str(self.project_root),
                env={**os.environ, "PYTHONUTF8": "1"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        return {
            "ok": process.returncode == 0,
            "exit_code": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace")[-30_000:],
            "stderr": stderr.decode("utf-8", errors="replace")[-12_000:],
        }
