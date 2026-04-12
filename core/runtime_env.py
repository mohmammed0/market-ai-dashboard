from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
_BOOTSTRAP_RESULT: dict[str, object] | None = None


def _strip_wrapping_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def load_local_env_file() -> dict[str, object]:
    global _BOOTSTRAP_RESULT
    if _BOOTSTRAP_RESULT is not None:
        return _BOOTSTRAP_RESULT

    env_path = ROOT_DIR / ".env"
    result: dict[str, object] = {
        "env_file_path": str(env_path),
        "env_file_found": env_path.exists(),
        "env_file_loaded": False,
        "applied_keys_count": 0,
        "skipped_existing_keys_count": 0,
        "parse_errors": 0,
        "mode": "process_environment_only",
    }

    if not env_path.exists():
        _BOOTSTRAP_RESULT = result
        return result

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = str(raw_line or "").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            result["parse_errors"] = int(result["parse_errors"]) + 1
            continue
        key, _, value = line.partition("=")
        key = str(key or "").strip()
        if not key:
            result["parse_errors"] = int(result["parse_errors"]) + 1
            continue
        if key in os.environ:
            result["skipped_existing_keys_count"] = int(result["skipped_existing_keys_count"]) + 1
            continue
        os.environ[key] = _strip_wrapping_quotes(value)
        result["applied_keys_count"] = int(result["applied_keys_count"]) + 1

    result["env_file_loaded"] = bool(result["applied_keys_count"])
    if result["env_file_found"]:
        result["mode"] = "process_environment_with_dotenv_fallback"
    _BOOTSTRAP_RESULT = result
    return result


ENV_BOOTSTRAP_INFO = load_local_env_file()
