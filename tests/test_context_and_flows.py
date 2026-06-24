import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deflow import context, flows, runner
from deflow.cli import build_parser
from deflow.config import Config, ConfigError


def make_lint_config(root: Path) -> Config:
    filelist_root = root / "filelists"
    filelist_root.mkdir()
    (filelist_root / "top.f").write_text("rtl/top.sv\n", encoding="utf-8")
    script = root / "lint.tcl"
    script.write_text("puts lint\n", encoding="utf-8")
    data = {
        "project": {
            "filelist_path": str(filelist_root),
            "common_file": str(filelist_root / "common.f"),
            "common_sim_file": str(filelist_root / "common_sim.f"),
            "spyglass_lib_file": str(root / "spyglass_lib.yaml"),
            "common_db_file": str(root / "common_db.yaml"),
            "sdc_path": str(root / "sdc"),
        },
        "tools": {"spyglass": {"executable": "spyglass"}},
        "flows": {
            "lint": {
                "tool": "spyglass",
                "work_path": str(root / "work"),
                "script": str(script),
                "defines": ["ASIC"],
                "waiver_path": str(root / "waiver"),
                "custom_policy_file": "",
            }
        },
    }
    return Config(data, root / "config.yaml", "lint")


def make_cdc_config(root: Path) -> Config:
    config = make_lint_config(root)
    cdc_script = root / "cdc.tcl"
    cdc_script.write_text("puts cdc\n", encoding="utf-8")
    data = {
        **config.data,
        "flows": {
            "cdc": {
                **config.data["flows"]["lint"],
                "script": str(cdc_script),
            }
        },
    }
    return Config(data, root / "config.yaml", "cdc")


class ContextAndFlowTests(unittest.TestCase):
    def test_fm_accepts_black_box_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["fm", "-d", "top", "-b", "memory,fifo"])
        self.assertEqual(args.black_box, ["memory", "fifo"])

    def test_fm_accepts_dc_run_time_argument(self):
        parser = build_parser()
        args = parser.parse_args(["fm", "-d", "top", "-time", "20260623_171200"])
        self.assertEqual(args.dc_time, "20260623_171200")
        with self.assertRaises(SystemExit):
            parser.parse_args(["fm", "-d", "top", "-time", "latest"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["fm", "-d", "top", "-time", "20260623_171200_123456"])

    def test_syn_does_not_expose_black_box_argument(self):
        parser = build_parser()
        args = parser.parse_args(["syn", "-d", "top"])
        self.assertFalse(hasattr(args, "black_box"))
        with self.assertRaises(SystemExit):
            parser.parse_args(["syn", "-d", "top", "-b", "memory"])

    def test_context_contains_data_but_no_flow_logic(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = make_lint_config(root_path)
            runtime = runner.prepare_runtime(config, "top")
            filelist = root_path / "filelists" / "top.f"
            context.write_context(config, runtime, "top", [filelist], ["memory"])
            text = runtime.context_file.read_text(encoding="utf-8")
            self.assertTrue(runtime.output_dir.is_dir())

        self.assertIn('set run_de(design) "top"', text)
        self.assertIn('set run_de(gui) "0"', text)
        self.assertIn("set run_de(output_dir)", text)
        self.assertIn('set run_de(defines) [list "ASIC"]', text)
        self.assertIn('set run_de(black_boxes) [list "memory"]', text)
        self.assertIn("set run_de(library_files) [list]", text)
        self.assertNotIn("run_goal", text)
        self.assertNotIn("new_project", text)

    def test_spyglass_context_loads_liberty_list(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = make_lint_config(root_path)
            liberty = root_path / "stdcell.lib"
            liberty.write_text("library(test) {}\n", encoding="utf-8")
            (root_path / "spyglass_lib.yaml").write_text(
                "libraries:\n  - stdcell.lib\n",
                encoding="utf-8",
            )
            runtime = runner.prepare_runtime(config, "top")
            filelist = root_path / "filelists" / "top.f"
            context.write_context(config, runtime, "top", [filelist], [])
            text = runtime.context_file.read_text(encoding="utf-8")

        self.assertIn(str(liberty).replace("\\", "\\\\"), text)

    def test_spyglass_rejects_db_before_tool_launch(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = make_lint_config(root_path)
            wrong_db = root_path / "stdcell.db"
            wrong_db.write_text("db\n", encoding="utf-8")
            (root_path / "spyglass_lib.yaml").write_text(
                "libraries:\n  - stdcell.db\n", encoding="utf-8"
            )
            runtime = runner.prepare_runtime(config, "top")
            filelist = root_path / "filelists" / "top.f"

            with self.assertRaisesRegex(ConfigError, "SpyGlass.*Liberty"):
                context.write_context(config, runtime, "top", [filelist], [])

    def test_dc_and_formality_contexts_share_db_list(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            base = make_lint_config(root_path)
            common_db = root_path / "stdcell.db"
            common_db.write_text("db\n", encoding="utf-8")
            (root_path / "common_db.yaml").write_text(
                "libraries:\n  - stdcell.db\n", encoding="utf-8"
            )
            filelist = root_path / "filelists" / "top.f"

            for flow_name, tool_name in (("syn", "dc"), ("fm", "formality")):
                with self.subTest(flow=flow_name):
                    flow = {
                        "tool": tool_name,
                        "work_path": str(root_path / flow_name),
                        "script": str(root_path / f"{flow_name}.tcl"),
                        "options": "",
                    }
                    constraint_post = root_path / "constraint_post.tcl"
                    dont_touch = root_path / "dont_touch.tcl"
                    dont_use_cell = root_path / "dont_use_cell.tcl"
                    if flow_name == "syn":
                        constraint_post.write_text(
                            "set_clock_uncertainty 0.1 [all_clocks]\n",
                            encoding="utf-8",
                        )
                        dont_touch.write_text(
                            "set_dont_touch [get_cells u_mem]\n",
                            encoding="utf-8",
                        )
                        dont_use_cell.write_text(
                            "set_dont_use [get_lib_cells */BAD*]\n",
                            encoding="utf-8",
                        )
                        flow["constraint_post_tcl"] = str(constraint_post)
                        flow["dont_touch_tcl"] = str(dont_touch)
                        flow["dont_use_cell_tcl"] = str(dont_use_cell)
                        flow["defines"] = ["TSMC_28HPC", "SYNTHESIS"]
                    data = {
                        "project": base.project,
                        "tools": {tool_name: {"executable": "tool"}},
                        "flows": {flow_name: flow},
                    }
                    config = Config(data, root_path / "config.yaml", flow_name)
                    runtime = runner.prepare_runtime(config, "top")
                    context.write_context(config, runtime, "top", [filelist], [])
                    text = runtime.context_file.read_text(encoding="utf-8")
                    self.assertIn(
                        str(common_db).replace("\\", "\\\\"), text
                    )
                    if flow_name == "syn":
                        self.assertIn(
                            str(constraint_post).replace("\\", "\\\\"), text
                        )
                        self.assertIn(
                            str(dont_touch).replace("\\", "\\\\"), text
                        )
                        self.assertIn(
                            str(dont_use_cell).replace("\\", "\\\\"), text
                        )
                        self.assertIn(
                            'set run_de(defines) [list "TSMC_28HPC" "SYNTHESIS"]',
                            text,
                        )

    def test_fm_time_context_points_to_dc_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            base = make_lint_config(root_path)
            timestamp = "20260623_171200"
            output_dir = root_path / "dc" / f"top_syn_{timestamp}" / "outputs"
            output_dir.mkdir(parents=True)
            impl_netlist = output_dir / "top_syn.v"
            svf_file = output_dir / "top_syn.svf"
            impl_netlist.write_text("module top; endmodule\n", encoding="utf-8")
            svf_file.write_text("svf\n", encoding="utf-8")
            data = {
                "project": base.project,
                "tools": {"formality": {"executable": "fm_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "dc"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                        "defines": ["TSMC_28HPC", "SYNTHESIS"],
                    },
                    "fm": {
                        "tool": "formality",
                        "work_path": str(root_path / "fm"),
                        "script": str(root_path / "fm.tcl"),
                        "options": "",
                    }
                },
            }
            config = Config(data, root_path / "config.yaml", "fm")
            runtime = runner.prepare_runtime(config, "top")
            filelist = root_path / "filelists" / "top.f"
            context.write_context(
                config,
                runtime,
                "top",
                [filelist],
                [],
                dc_time=timestamp,
            )
            text = runtime.context_file.read_text(encoding="utf-8")

        self.assertIn(str(impl_netlist).replace("\\", "\\\\"), text)
        self.assertIn(str(svf_file).replace("\\", "\\\\"), text)
        self.assertIn(
            'set run_de(defines) [list "TSMC_28HPC" "SYNTHESIS"]',
            text,
        )

    def test_fm_time_rejects_missing_dc_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            base = make_lint_config(root_path)
            data = {
                "project": base.project,
                "tools": {"formality": {"executable": "fm_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "dc"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                    },
                    "fm": {
                        "tool": "formality",
                        "work_path": str(root_path / "fm"),
                        "script": str(root_path / "fm.tcl"),
                        "options": "",
                    }
                },
            }
            config = Config(data, root_path / "config.yaml", "fm")
            runtime = runner.prepare_runtime(config, "top")
            filelist = root_path / "filelists" / "top.f"

            with self.assertRaisesRegex(ConfigError, "implementation netlist"):
                context.write_context(
                    config,
                    runtime,
                    "top",
                    [filelist],
                    [],
                    dc_time="20260623_171200",
                )

    def test_missing_constraint_post_tcl_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            base = make_lint_config(root_path)
            filelist = root_path / "filelists" / "top.f"
            data = {
                "project": base.project,
                "tools": {"dc": {"executable": "dc_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "syn"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                        "constraint_post_tcl": str(root_path / "missing.tcl"),
                    }
                },
            }
            config = Config(data, root_path / "config.yaml", "syn")
            runtime = runner.prepare_runtime(config, "top")

            with self.assertRaisesRegex(ConfigError, "constraint post Tcl"):
                context.write_context(config, runtime, "top", [filelist], [])

    def test_missing_dont_touch_tcl_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            base = make_lint_config(root_path)
            filelist = root_path / "filelists" / "top.f"
            data = {
                "project": base.project,
                "tools": {"dc": {"executable": "dc_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "syn"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                        "dont_touch_tcl": str(root_path / "missing.tcl"),
                    }
                },
            }
            config = Config(data, root_path / "config.yaml", "syn")
            runtime = runner.prepare_runtime(config, "top")

            with self.assertRaisesRegex(ConfigError, "dont touch Tcl"):
                context.write_context(config, runtime, "top", [filelist], [])

    def test_missing_dont_use_cell_tcl_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            base = make_lint_config(root_path)
            filelist = root_path / "filelists" / "top.f"
            data = {
                "project": base.project,
                "tools": {"dc": {"executable": "dc_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "syn"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                        "dont_use_cell_tcl": str(root_path / "missing.tcl"),
                    }
                },
            }
            config = Config(data, root_path / "config.yaml", "syn")
            runtime = runner.prepare_runtime(config, "top")

            with self.assertRaisesRegex(ConfigError, "dont-use cell Tcl"):
                context.write_context(config, runtime, "top", [filelist], [])

    def test_spyglass_flow_uses_pty_runner_and_propagates_exit_code(self):
        with tempfile.TemporaryDirectory() as root:
            config = make_lint_config(Path(root))
            with mock.patch.object(flows.runner, "run_pty_process", return_value=23) as run:
                code = flows.run_flow(config, "top", black_boxes=["memory"])

            self.assertEqual(code, 23)
            args = run.call_args.args[1]
            self.assertEqual(args[:2], ["-shell", "-tcl"])
            self.assertEqual(Path(args[2]), config.path_value(config.flow["script"]))
            self.assertIn("RUN_DE_CONTEXT", run.call_args.kwargs["env"])

    def test_cdc_flow_uses_pty_runner(self):
        with tempfile.TemporaryDirectory() as root:
            config = make_cdc_config(Path(root))
            with mock.patch.object(flows.runner, "run_pty_process", return_value=0) as run:
                code = flows.run_flow(config, "top")

            self.assertEqual(code, 0)
            args = run.call_args.args[1]
            self.assertEqual(args[:2], ["-shell", "-tcl"])
            self.assertEqual(Path(args[2]), config.path_value(config.flow["script"]))

    def test_syn_flow_attaches_terminal_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = make_lint_config(root_path)
            data = {
                "project": config.project,
                "tools": {"dc": {"executable": "dc_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "syn"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                    }
                },
            }
            syn_config = Config(data, root_path / "config.yaml", "syn")
            (root_path / "syn.tcl").write_text("puts syn\n", encoding="utf-8")

            with mock.patch.object(
                flows.runner, "run_interactive_process", return_value=0
            ) as run:
                code = flows.run_flow(syn_config, "top")

            self.assertEqual(code, 0)
            args = run.call_args.args[1]
            self.assertEqual(args[0], "-output_log_file")
            self.assertTrue(args[1].endswith("run.log"))
            self.assertEqual(args[2:4], ["-f", str(root_path / "syn.tcl")])
            self.assertIn("RUN_DE_CONTEXT", run.call_args.kwargs["env"])

    def test_fm_flow_uses_pty_runner_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = make_lint_config(root_path)
            data = {
                "project": config.project,
                "tools": {"formality": {"executable": "fm_shell"}},
                "flows": {
                    "syn": {
                        "tool": "dc",
                        "work_path": str(root_path / "syn"),
                        "script": str(root_path / "syn.tcl"),
                        "options": "",
                        "defines": ["TSMC_28HPC"],
                    },
                    "fm": {
                        "tool": "formality",
                        "work_path": str(root_path / "fm"),
                        "script": str(root_path / "fm.tcl"),
                        "options": "",
                    },
                },
            }
            fm_config = Config(data, root_path / "config.yaml", "fm")
            (root_path / "fm.tcl").write_text("puts fm\n", encoding="utf-8")

            with mock.patch.object(flows.runner, "run_pty_process", return_value=0) as run:
                code = flows.run_flow(fm_config, "top")

            self.assertEqual(code, 0)
            args = run.call_args.args[1]
            self.assertEqual(args[:2], ["-f", str(root_path / "fm.tcl")])
            self.assertNotIn("-output_log_file", args)
            self.assertIn("RUN_DE_CONTEXT", run.call_args.kwargs["env"])

    def test_gui_mode_is_written_to_context(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = make_lint_config(root_path)
            runtime = runner.prepare_runtime(config, "top")
            filelist = root_path / "filelists" / "top.f"
            context.write_context(
                config, runtime, "top", [filelist], [], gui=True
            )
            text = runtime.context_file.read_text(encoding="utf-8")

        self.assertIn('set run_de(gui) "1"', text)


if __name__ == "__main__":
    unittest.main()
