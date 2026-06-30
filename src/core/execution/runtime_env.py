"""Runtime environment defaults for subprocesses started by MAESTRO."""

import os
from pathlib import Path
from typing import Mapping, MutableMapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]

LOCAL_CACHE_DEFAULTS = {
    "UV_CACHE_DIR": PROJECT_ROOT / ".uv-cache",
    "npm_config_cache": PROJECT_ROOT / ".tmp" / "npm-cache",
}

NPM_RUNTIME_DEFAULTS = {
    "npm_config_prefer_offline": "true",
    "npm_config_update_notifier": "false",
    "npm_config_audit": "false",
    "npm_config_fund": "false",
}


def configure_local_runtime_environment(
    env: MutableMapping[str, str] = os.environ,
) -> None:
    """Set local cache defaults without overriding explicit user configuration."""
    for name, path in LOCAL_CACHE_DEFAULTS.items():
        if env.get(name):
            continue
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    for name, value in NPM_RUNTIME_DEFAULTS.items():
        env.setdefault(name, value)


def build_subprocess_env(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    configure_local_runtime_environment()
    env = os.environ.copy()
    if overrides:
        env.update({key: value for key, value in overrides.items() if value is not None})
    return env
