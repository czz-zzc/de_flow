"""Generate a data-only Tcl context for tool-maintained flow scripts."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from deflow.config import Config, ConfigError
from deflow.runner import Runtime


def _tcl_quote(value: Any) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
    return f'"{escaped}"'


def _tcl_list(values: list[Any]) -> str:
    return "[list" + "".join(f" {_tcl_quote(value)}" for value in values) + "]"


def _optional_file(path: Path) -> str:
    return str(path) if path.is_file() else ""


def _resolve_waiver(config: Config, design: str) -> str:
    value = config.flow.get("waiver_path", "")
    if not value:
        return ""
    return _optional_file(config.path_value(value) / f"{design}.awl")


def _resolve_libraries(config: Config) -> list[str]:
    """Resolve SpyGlass Liberty files or the shared DC/Formality DB files."""
    tool_name = config.flow["tool"]
    if tool_name == "spyglass":
        manifest_key = "spyglass_lib_file"
    elif tool_name in ("dc", "formality"):
        manifest_key = "common_db_file"
    else:
        return []

    manifest = config.path_value(config.project[manifest_key])
    if not manifest.is_file():
        return []
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid library manifest {manifest}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ConfigError(f"Library manifest must be a YAML mapping: {manifest}")

    values = data.get("libraries", [])
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ConfigError(
            f"Library manifest 'libraries' entry must be a list of paths: {manifest}"
        )

    result: list[str] = []
    for value in values:
        expanded = os.path.expandvars(value)
        path = Path(expanded)
        if not path.is_absolute():
            path = manifest.parent / path
        path = path.resolve()
        if not path.is_file():
            raise ConfigError(f"Library file not found: {path}")
        lower_name = path.name.lower()
        if tool_name == "spyglass" and not (
            lower_name.endswith(".lib") or lower_name.endswith(".lib.gz")
        ):
            raise ConfigError(
                f"SpyGlass library must be a Liberty .lib or .lib.gz file: {path}"
            )
        if tool_name in ("dc", "formality") and not lower_name.endswith(".db"):
            raise ConfigError(
                f"{tool_name} library must be a Synopsys .db file: {path}"
            )
        result.append(str(path))
    return result


def _resolve_policy(config: Config) -> str:
    value = config.flow.get("custom_policy_file", "")
    return _optional_file(config.path_value(value)) if value else ""


def _resolve_tcl_hook(config: Config, key: str, description: str) -> str:
    value = config.flow.get(key, "")
    if not value:
        return ""
    path = config.path_value(value)
    if not path.is_file():
        raise ConfigError(f"{description} not found: {path}")
    return str(path)


def _resolve_fm_artifacts(
    config: Config,
    design: str,
    dc_time: str | None,
) -> dict[str, str]:
    if config.flow_name != "fm" or dc_time is None:
        return {"impl_netlist": "", "svf_file": ""}
    syn_flow = config.data.get("flows", {}).get("syn", {})
    if not isinstance(syn_flow, Mapping):
        raise ConfigError("flows.syn is required when fm -time is used")
    value = syn_flow.get("work_path", "")
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("flows.syn.work_path is required when fm -time is used")

    output_dir = (
        config.path_value(value) / f"{design}_syn_{dc_time}" / "outputs"
    )
    impl_netlist = output_dir / f"{design}_syn.v"
    svf_file = output_dir / f"{design}_syn.svf"
    for path, description in (
        (impl_netlist, "Formality implementation netlist"),
        (svf_file, "Formality SVF file"),
    ):
        if not path.is_file():
            raise ConfigError(f"{description} not found: {path}")
    return {"impl_netlist": str(impl_netlist), "svf_file": str(svf_file)}


def _resolve_defines(config: Config) -> list[str]:
    flow_defines = config.flow.get("defines", [])
    if config.flow_name == "fm":
        syn_flow = config.data.get("flows", {}).get("syn", {})
        if isinstance(syn_flow, Mapping):
            flow_defines = syn_flow.get("defines", flow_defines)
    if not isinstance(flow_defines, list) or any(
        not isinstance(item, str) for item in flow_defines
    ):
        raise ConfigError("flow defines must be a list of strings")
    return flow_defines


def write_context(
    config: Config,
    runtime: Runtime,
    design: str,
    filelists: list[Path],
    black_boxes: list[str],
    gui: bool = False,
    dc_time: str | None = None,
) -> Path:
    """Write all run-specific data; no EDA flow logic belongs here."""
    sdc = config.path_value(config.project["sdc_path"]) / f"{design}.sdc"
    fm_artifacts = _resolve_fm_artifacts(config, design, dc_time)
    scalars = {
        "flow": config.flow_name,
        "gui": "1" if gui else "0",
        "design": design,
        "work_dir": runtime.work_dir,
        "report_dir": runtime.report_dir,
        "output_dir": runtime.output_dir,
        "sdc_file": _optional_file(sdc),
        "waiver_file": _resolve_waiver(config, design),
        "custom_policy_file": _resolve_policy(config),
        "constraint_post_tcl": _resolve_tcl_hook(
            config, "constraint_post_tcl", "constraint post Tcl"
        ),
        "dont_touch_tcl": _resolve_tcl_hook(
            config, "dont_touch_tcl", "dont touch Tcl"
        ),
        "dont_use_cell_tcl": _resolve_tcl_hook(
            config, "dont_use_cell_tcl", "dont-use cell Tcl"
        ),
        **fm_artifacts,
    }
    lists = {
        "filelists": [str(path) for path in filelists],
        "defines": _resolve_defines(config),
        "black_boxes": black_boxes,
        "library_files": _resolve_libraries(config),
    }

    lines = [
        "# Data-only file generated by run_de. Flow logic belongs in tcl/*.tcl.",
        "array set run_de {}",
    ]
    lines.extend(f"set run_de({key}) {_tcl_quote(value)}" for key, value in scalars.items())
    lines.extend(f"set run_de({key}) {_tcl_list(value)}" for key, value in lists.items())
    runtime.context_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime.context_file
