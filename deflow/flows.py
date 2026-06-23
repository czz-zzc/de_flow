"""Flow registry and the small set of supported execution adapters."""

from dataclasses import dataclass
from pathlib import Path

from deflow import context, runner
from deflow.config import Config


@dataclass(frozen=True)
class FlowSpec:
    kind: str
    batch_prefix: tuple[str, ...] = ()
    gui_prefix: tuple[str, ...] = ()


FLOW_SPECS = {
    "compile": FlowSpec("compile"),
    "verdi": FlowSpec("verdi"),
    "lint": FlowSpec("tcl", ("-shell", "-tcl"), ("-tcl",)),
    "cdc": FlowSpec("tcl", ("-shell", "-tcl"), ("-tcl",)),
    "syn": FlowSpec("tcl", ("-f",)),
    "fm": FlowSpec("tcl", ("-f",)),
}


def _filelists(config: Config, design: str, *, tcl_flow: bool) -> list[Path]:
    include_common = config.flow.get("include_common", True)
    include_sim = config.flow.get("include_sim", False if tcl_flow else True)
    return runner.resolve_filelists(
        config,
        design,
        include_common=include_common,
        include_sim=include_sim,
    )


def _run_compile(config: Config, design: str) -> int:
    filelists = _filelists(config, design, tcl_flow=False)
    runtime = runner.prepare_runtime(config, design)
    args: list[str] = []
    for filelist in filelists:
        args.extend(("-f", str(filelist)))
    args.extend(("-top", design))
    args.extend(runner.split_options(config.flow["options"]))
    return runner.run_process(config.executable, args, runtime)


def _run_verdi(config: Config, design: str) -> int:
    filelists = _filelists(config, design, tcl_flow=False)
    runtime = runner.prepare_runtime(config, design)
    args = ["-top", design]
    for filelist in filelists:
        args.extend(("-f", str(filelist)))
    args.extend(runner.split_options(config.flow["options"]))
    return runner.launch_process(config.executable, args, runtime)


def _run_tcl(
    config: Config,
    spec: FlowSpec,
    design: str,
    black_boxes: list[str],
    gui: bool,
    dc_time: str | None,
) -> int:
    script = config.path_value(config.flow["script"])
    if not script.is_file():
        raise runner.FlowError(f"Flow TCL script not found: {script}")
    filelists = _filelists(config, design, tcl_flow=True)
    runtime = runner.prepare_runtime(config, design)
    context.write_context(
        config,
        runtime,
        design,
        filelists,
        black_boxes,
        gui=gui,
        dc_time=dc_time,
    )

    prefix = spec.gui_prefix if gui and spec.gui_prefix else spec.batch_prefix
    configured_options = runner.split_options(config.flow.get("options", ""))
    args = [*configured_options, *prefix, str(script)]
    if config.flow_name == "syn":
        args = ["-output_log_file", str(runtime.log_file), *args]
        return runner.run_interactive_process(
            config.executable,
            args,
            runtime,
            env={"RUN_DE_CONTEXT": str(runtime.context_file)},
        )
    if config.flow_name == "fm":
        return runner.run_interactive_process(
            config.executable,
            args,
            runtime,
            env={"RUN_DE_CONTEXT": str(runtime.context_file)},
        )
    return runner.run_process(
        config.executable,
        args,
        runtime,
        env={"RUN_DE_CONTEXT": str(runtime.context_file)},
    )


def run_flow(
    config: Config,
    design: str,
    *,
    black_boxes: list[str] | None = None,
    gui: bool = False,
    dc_time: str | None = None,
) -> int:
    """Run the selected flow through its registered adapter."""
    runner.validate_design(design)
    boxes = black_boxes or []
    for box in boxes:
        runner.validate_design(box)
    if dc_time is not None:
        runner.validate_timestamp(dc_time)

    spec = FLOW_SPECS[config.flow_name]
    if spec.kind == "compile":
        return _run_compile(config, design)
    if spec.kind == "verdi":
        return _run_verdi(config, design)
    return _run_tcl(config, spec, design, boxes, gui, dc_time)
