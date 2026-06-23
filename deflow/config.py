"""Configuration loading, expansion, and per-flow validation."""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(ValueError):
    """Raised when run_de configuration is missing or invalid."""


_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
_PROJECT_FIELDS = {
    "filelist_path": str,
    "common_file": str,
    "common_sim_file": str,
    "spyglass_lib_file": str,
    "common_db_file": str,
    "sdc_path": str,
}
_FLOW_FIELDS = {
    "compile": {
        "tool": str,
        "work_path": str,
        "options": str,
        "include_common": bool,
        "include_sim": bool,
    },
    "verdi": {
        "tool": str,
        "work_path": str,
        "options": str,
        "include_common": bool,
        "include_sim": bool,
    },
    "lint": {
        "tool": str,
        "work_path": str,
        "script": str,
        "defines": list,
        "waiver_path": str,
        "custom_policy_file": str,
    },
    "cdc": {
        "tool": str,
        "work_path": str,
        "script": str,
        "defines": list,
        "waiver_path": str,
        "custom_policy_file": str,
    },
    "syn": {"tool": str, "work_path": str, "script": str, "options": str},
    "fm": {"tool": str, "work_path": str, "script": str, "options": str},
}
_OPTIONAL_FLOW_FIELDS = {
    "syn": {
        "defines": list,
        "constraint_post_tcl": str,
        "dont_touch_tcl": str,
        "dont_use_cell_tcl": str,
    },
}
_ALLOW_EMPTY = {
    "flows.compile.options",
    "flows.verdi.options",
    "flows.syn.options",
    "flows.syn.constraint_post_tcl",
    "flows.syn.dont_touch_tcl",
    "flows.syn.dont_use_cell_tcl",
    "flows.fm.options",
    "flows.lint.custom_policy_file",
    "flows.cdc.custom_policy_file",
}


def _referenced_vars(value: Any) -> set[str]:
    if isinstance(value, str):
        return {match.group(1) or match.group(2) for match in _VAR_PATTERN.finditer(value)}
    if isinstance(value, Mapping):
        result: set[str] = set()
        for item in value.values():
            result.update(_referenced_vars(item))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(_referenced_vars(item))
        return result
    return set()


def _expand(value: Any, variables: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _VAR_PATTERN.sub(
            lambda match: variables[match.group(1) or match.group(2)], value
        )
    if isinstance(value, Mapping):
        return {key: _expand(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item, variables) for item in value]
    return value


def _validate_fields(
    section: Any,
    fields: Mapping[str, type],
    prefix: str,
    errors: list[str],
) -> None:
    if not isinstance(section, Mapping):
        errors.append(f"'{prefix}' must be a mapping")
        return
    for name, expected_type in fields.items():
        dotted = f"{prefix}.{name}"
        if name not in section:
            errors.append(f"missing '{dotted}'")
            continue
        value = section[name]
        if not isinstance(value, expected_type):
            errors.append(f"'{dotted}' must be {expected_type.__name__}")
            continue
        if isinstance(value, str) and not value.strip() and dotted not in _ALLOW_EMPTY:
            errors.append(f"'{dotted}' cannot be empty")
        if isinstance(value, list) and any(not isinstance(item, str) for item in value):
            errors.append(f"'{dotted}' must contain only strings")


def _validate_optional_fields(
    section: Any,
    fields: Mapping[str, type],
    prefix: str,
    errors: list[str],
) -> None:
    if not isinstance(section, Mapping):
        return
    for name, expected_type in fields.items():
        if name not in section:
            continue
        dotted = f"{prefix}.{name}"
        value = section[name]
        if not isinstance(value, expected_type):
            errors.append(f"'{dotted}' must be {expected_type.__name__}")
            continue
        if isinstance(value, str) and not value.strip() and dotted not in _ALLOW_EMPTY:
            errors.append(f"'{dotted}' cannot be empty")
        if isinstance(value, list) and any(not isinstance(item, str) for item in value):
            errors.append(f"'{dotted}' must contain only strings")


def _validate(data: Any, flow_name: Optional[str]) -> None:
    if not isinstance(data, Mapping):
        raise ConfigError("Configuration root must be a YAML mapping")

    errors: list[str] = []
    _validate_fields(data.get("project"), _PROJECT_FIELDS, "project", errors)

    if flow_name is None:
        if errors:
            raise ConfigError("Invalid configuration:\n- " + "\n- ".join(errors))
        return
    if flow_name not in _FLOW_FIELDS:
        raise ConfigError(f"Unknown flow: {flow_name}")

    flows = data.get("flows")
    if not isinstance(flows, Mapping):
        errors.append("'flows' must be a mapping")
        selected_flow = None
    else:
        selected_flow = flows.get(flow_name)
    _validate_fields(
        selected_flow, _FLOW_FIELDS[flow_name], f"flows.{flow_name}", errors
    )
    _validate_optional_fields(
        selected_flow,
        _OPTIONAL_FLOW_FIELDS.get(flow_name, {}),
        f"flows.{flow_name}",
        errors,
    )

    if isinstance(selected_flow, Mapping) and isinstance(selected_flow.get("tool"), str):
        tool_name = selected_flow["tool"]
        tools = data.get("tools")
        tool = tools.get(tool_name) if isinstance(tools, Mapping) else None
        _validate_fields(tool, {"executable": str}, f"tools.{tool_name}", errors)

    if errors:
        raise ConfigError("Invalid configuration:\n- " + "\n- ".join(errors))


class Config:
    """Validated configuration for one selected flow."""

    def __init__(self, data: dict[str, Any], path: Path, flow_name: Optional[str]):
        self.data = data
        self.path = path
        self.flow_name = flow_name

    @property
    def project(self) -> dict[str, Any]:
        return self.data["project"]

    @property
    def flow(self) -> dict[str, Any]:
        if self.flow_name is None:
            raise ConfigError("No flow was selected")
        return self.data["flows"][self.flow_name]

    @property
    def executable(self) -> str:
        return self.data["tools"][self.flow["tool"]]["executable"]

    def path_value(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.path.parent / path
        return path.resolve()


def load_config(
    flow_name: Optional[str],
    config_path: Optional[str] = None,
) -> Config:
    """Load and validate only the common and selected-flow configuration."""
    project_root = Path(__file__).resolve().parents[1]
    path = Path(config_path) if config_path else project_root / "run_de_config.yaml"
    path = path.resolve()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if isinstance(raw, Mapping):
        raw_flows = raw.get("flows")
        selected = (
            raw_flows.get(flow_name)
            if flow_name is not None and isinstance(raw_flows, Mapping)
            else None
        )
        selected_flows = {flow_name: selected} if flow_name is not None else {}
        if flow_name == "fm" and isinstance(raw_flows, Mapping):
            selected_flows["syn"] = raw_flows.get("syn")
        scoped_raw = {
            "project": raw.get("project"),
            "tools": raw.get("tools"),
            "flows": selected_flows,
        }
    else:
        scoped_raw = raw

    variables = dict(os.environ)
    variables["RUN_DE_HOME"] = str(project_root)
    missing = sorted(
        name for name in _referenced_vars(scoped_raw) if not variables.get(name)
    )
    if missing:
        raise ConfigError(
            "Required environment variable(s) not set: " + ", ".join(missing)
        )

    data = _expand(scoped_raw, variables)
    _validate(data, flow_name)
    return Config(data, path, flow_name)
