"""Single command-line entry point for all run_de flows."""

import argparse
import sys
from typing import Optional, Sequence

from deflow import flows, runner
from deflow.config import ConfigError, load_config


_DESCRIPTIONS = {
    "compile": "Compile RTL design with VCS",
    "verdi": "Open RTL design in Verdi",
    "lint": "Run SpyGlass lint",
    "cdc": "Run SpyGlass CDC",
    "syn": "Run Design Compiler synthesis",
    "fm": "Run Formality equivalence checking",
}


def _design_arg(value: str) -> str:
    try:
        return runner.validate_design(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _module_list(value: str) -> list[str]:
    result = [item.strip() for item in value.split(",") if item.strip()]
    if not result:
        raise argparse.ArgumentTypeError("cannot be empty")
    for item in result:
        _design_arg(item)
    return result


def _dc_time_arg(value: str) -> str:
    try:
        return runner.validate_timestamp(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_de", description="Chip Design Flow Manager")
    parser.add_argument(
        "-c", "--config", help="Configuration file (default: run_de_config.yaml)"
    )
    parser.add_argument(
        "-list",
        "--list",
        action="store_true",
        dest="list_designs",
        help="List designs found in project.filelist_path",
    )
    subparsers = parser.add_subparsers(dest="flow", metavar="<flow>")
    for name, description in _DESCRIPTIONS.items():
        subparser = subparsers.add_parser(name, help=description, description=description)
        subparser.add_argument(
            "-d", "--design", required=True, type=_design_arg, help="Top module name"
        )
        if name in ("lint", "cdc", "fm"):
            subparser.add_argument(
                "-b",
                "--black-box",
                action="extend",
                default=[],
                type=_module_list,
                help="Comma-separated black-box modules; may be repeated",
            )
            if name in ("lint", "cdc"):
                subparser.add_argument(
                    "-gui", "--gui", action="store_true", help="Launch SpyGlass GUI"
                )
            if name == "fm":
                subparser.add_argument(
                    "-time",
                    "--time",
                    dest="dc_time",
                    type=_dc_time_arg,
                    help="DC run timestamp used to locate outputs/<design>_syn.v and .svf",
                )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_designs:
        try:
            config = load_config(None, args.config)
            designs = runner.list_designs(config)
            print(f"Filelist directory: {config.path_value(config.project['filelist_path'])}")
            print(f"Designs ({len(designs)}):")
            for design in designs:
                print(f"  {design}")
            return 0
        except (ConfigError, runner.FlowError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.flow is None:
        parser.print_help()
        return 0
    try:
        config = load_config(args.flow, args.config)
        return flows.run_flow(
            config,
            args.design,
            black_boxes=getattr(args, "black_box", []),
            gui=getattr(args, "gui", False),
            dc_time=getattr(args, "dc_time", None),
        )
    except (ConfigError, runner.FlowError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
