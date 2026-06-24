"""Shared runtime preparation and shell-free process execution."""

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional, Sequence

import yaml

from deflow.config import Config


class FlowError(RuntimeError):
    """Raised when a flow cannot be prepared or executed."""


_DESIGN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_TIMESTAMP_PATTERN = re.compile(r"\d{8}_\d{6}\Z")


def validate_design(value: str) -> str:
    if not _DESIGN_PATTERN.fullmatch(value):
        raise ValueError(
            f"invalid design name {value!r}; expected [A-Za-z_][A-Za-z0-9_]*"
        )
    return value


def validate_timestamp(value: str) -> str:
    if not _TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError(
            f"invalid DC run timestamp {value!r}; expected YYYYMMDD_HHMMSS"
        )
    return value


def split_options(options: str) -> list[str]:
    try:
        return shlex.split(options, posix=True)
    except ValueError as exc:
        raise FlowError(f"Invalid tool option string: {exc}") from exc


def resolve_filelists(
    config: Config,
    design: str,
    *,
    include_common: bool,
    include_sim: bool,
) -> list[Path]:
    validate_design(design)
    root = config.path_value(config.project["filelist_path"])
    main = root / f"{design}.f"
    if not main.is_file():
        raise FlowError(f"Design filelist not found: {main}")

    result = [main]
    keys: list[str] = []
    if include_common:
        keys.append("common_file")
    if include_sim:
        keys.append("common_sim_file")
    for key in keys:
        candidate = config.path_value(config.project[key])
        if candidate.is_file() and candidate not in result:
            result.append(candidate)
    return result


def list_designs(config: Config) -> list[str]:
    """List runnable designs represented by top-level ``*.f`` filelists."""
    root = config.path_value(config.project["filelist_path"])
    if not root.is_dir():
        raise FlowError(f"Filelist directory not found: {root}")

    excluded = {
        config.path_value(config.project["common_file"]),
        config.path_value(config.project["common_sim_file"]),
    }
    designs: list[str] = []
    for filelist in root.glob("*.f"):
        if filelist.resolve() in excluded:
            continue
        try:
            designs.append(validate_design(filelist.stem))
        except ValueError:
            continue
    return sorted(set(designs), key=str.casefold)


@dataclass(frozen=True)
class Runtime:
    work_dir: Path
    report_dir: Path
    output_dir: Path
    log_file: Path
    context_file: Path
    command_file: Path
    config_file: Path


def prepare_runtime(config: Config, design: str) -> Runtime:
    validate_design(design)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_root = config.path_value(config.flow["work_path"])
    work_dir = work_root / f"{design}_{config.flow_name}_{stamp}"
    report_dir = work_dir / "reports"
    output_dir = work_dir / "outputs"
    report_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=False, exist_ok=False)

    runtime = Runtime(
        work_dir=work_dir,
        report_dir=report_dir,
        output_dir=output_dir,
        log_file=work_dir / "run.log",
        context_file=work_dir / "run_context.tcl",
        command_file=work_dir / "command.txt",
        config_file=work_dir / "resolved_config.yaml",
    )
    snapshot = {
        "project": config.project,
        "tool": config.data["tools"][config.flow["tool"]],
        "flow": config.flow,
    }
    runtime.config_file.write_text(
        yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return runtime


def require_executable(program: str) -> Path:
    candidate = Path(program)
    if candidate.parent != Path("."):
        if candidate.is_file():
            return candidate.resolve()
        raise FlowError(f"Tool executable not found: {candidate}")
    found = shutil.which(program)
    if found is None:
        raise FlowError(f"'{program}' not found in PATH; source the EDA environment first")
    return Path(found)


def _command_text(command: Sequence[str]) -> str:
    return shlex.join(map(str, command))


def run_process(
    executable: str,
    args: Sequence[str],
    runtime: Runtime,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """Run a tool without a shell, tee output, and preserve its exit code."""
    program = require_executable(executable)
    command = [str(program), *map(str, args)]
    runtime.command_file.write_text(_command_text(command) + "\n", encoding="utf-8")
    merged_env = {**os.environ, **dict(env or {})}

    try:
        process = subprocess.Popen(
            command,
            cwd=runtime.work_dir,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        raise FlowError(f"Failed to start {executable}: {exc}") from exc
    assert process.stdout is not None
    with runtime.log_file.open("w", encoding="utf-8") as log:
        try:
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="")
        finally:
            process.stdout.close()
    return process.wait()


def run_interactive_process(
    executable: str,
    args: Sequence[str],
    runtime: Runtime,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """Run a tool attached directly to the current terminal."""
    program = require_executable(executable)
    command = [str(program), *map(str, args)]
    runtime.command_file.write_text(_command_text(command) + "\n", encoding="utf-8")
    merged_env = {**os.environ, **dict(env or {})}

    try:
        process = subprocess.Popen(command, cwd=runtime.work_dir, env=merged_env)
    except OSError as exc:
        raise FlowError(f"Failed to start {executable}: {exc}") from exc
    return process.wait()


class _OutputTee:
    def __init__(self, log):
        self.log = log

    def write(self, data: str) -> None:
        self.log.write(data)
        self.log.flush()
        sys.stdout.write(data)
        sys.stdout.flush()

    def flush(self) -> None:
        self.log.flush()
        sys.stdout.flush()


def run_pty_process(
    executable: str,
    args: Sequence[str],
    runtime: Runtime,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """Run through a pseudo-terminal, teeing output to screen and run.log."""
    if sys.platform == "win32":
        return run_process(executable, args, runtime, env=env)
    try:
        import pexpect
    except ImportError:
        return run_process(executable, args, runtime, env=env)

    program = require_executable(executable)
    command = [str(program), *map(str, args)]
    runtime.command_file.write_text(_command_text(command) + "\n", encoding="utf-8")
    merged_env = {**os.environ, **dict(env or {})}

    try:
        child = pexpect.spawn(
            str(program),
            list(map(str, args)),
            cwd=str(runtime.work_dir),
            env=merged_env,
            encoding="utf-8",
            codec_errors="replace",
            echo=False,
        )
    except OSError as exc:
        raise FlowError(f"Failed to start {executable}: {exc}") from exc

    with runtime.log_file.open("w", encoding="utf-8") as log:
        try:
            if sys.stdin.isatty():
                def log_output(data):
                    text = (
                        data.decode("utf-8", errors="replace")
                        if isinstance(data, bytes)
                        else data
                    )
                    log.write(text)
                    log.flush()
                    return data

                child.interact(output_filter=log_output)
            else:
                child.logfile_read = _OutputTee(log)
                child.expect(pexpect.EOF, timeout=None)
        finally:
            child.close()
    return child.exitstatus if child.exitstatus is not None else 1


def launch_process(executable: str, args: Sequence[str], runtime: Runtime) -> int:
    """Launch a GUI process in the background without a shell."""
    program = require_executable(executable)
    command = [str(program), *map(str, args)]
    runtime.command_file.write_text(_command_text(command) + "\n", encoding="utf-8")
    try:
        if sys.platform == "win32":
            subprocess.Popen(command, cwd=runtime.work_dir, creationflags=0x08000000)
        else:
            subprocess.Popen(command, cwd=runtime.work_dir, start_new_session=True)
    except OSError as exc:
        raise FlowError(f"Failed to start {executable}: {exc}") from exc
    runtime.log_file.write_text("Process launched in background.\n", encoding="utf-8")
    return 0
