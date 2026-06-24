import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from deflow import runner
from deflow.config import Config


def make_config(root: Path, flow_name: str = "compile") -> Config:
    data = {
        "project": {
            "filelist_path": str(root / "filelists"),
            "common_file": str(root / "filelists" / "common.f"),
            "common_sim_file": str(root / "filelists" / "common_sim.f"),
            "spyglass_lib_file": str(root / "spyglass_lib.yaml"),
            "common_db_file": str(root / "common_db.yaml"),
            "sdc_path": str(root / "sdc"),
        },
        "tools": {"tool": {"executable": "fake"}},
        "flows": {
            flow_name: {
                "tool": "tool",
                "work_path": str(root / "work"),
                "options": "",
            }
        },
    }
    return Config(data, root / "config.yaml", flow_name)


class RunnerTests(unittest.TestCase):
    def test_design_validation(self):
        self.assertEqual(runner.validate_design("top_2"), "top_2")
        for invalid in ("", "2top", "top.core", "top; echo bad", "top module"):
            with self.assertRaises(ValueError):
                runner.validate_design(invalid)

    def test_filelist_resolution(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            filelist_root = root_path / "filelists"
            filelist_root.mkdir()
            files = [
                filelist_root / "top.f",
                filelist_root / "common.f",
                filelist_root / "common_sim.f",
            ]
            for path in files:
                path.write_text("", encoding="utf-8")
            config = make_config(root_path)
            result = runner.resolve_filelists(
                config, "top", include_common=True, include_sim=True
            )
            self.assertEqual(result, files)

    def test_real_process_exit_code_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = runner.prepare_runtime(make_config(Path(root)), "top")
            with mock.patch.object(
                runner, "require_executable", return_value=Path(sys.executable)
            ):
                code = runner.run_process(
                    "fake", ["-c", "import sys; sys.exit(37)"], runtime
                )
            self.assertEqual(code, 37)
            self.assertIn("sys.exit(37)", runtime.command_file.read_text())

    def test_pty_process_falls_back_to_pipe_on_windows(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = runner.prepare_runtime(make_config(Path(root)), "top")
            with mock.patch.object(runner.sys, "platform", "win32"):
                with mock.patch.object(runner, "run_process", return_value=11) as run:
                    code = runner.run_pty_process("fake", ["-f", "fm.tcl"], runtime)

            self.assertEqual(code, 11)
            run.assert_called_once_with("fake", ["-f", "fm.tcl"], runtime, env=None)

    def test_pty_process_interacts_when_stdin_is_tty(self):
        class FakeChild:
            exitstatus = 0

            def __init__(self):
                self.interacted = False
                self.closed = False

            def interact(self, output_filter=None):
                self.interacted = True
                if output_filter is not None:
                    self.filtered = output_filter(b"fm_shell> ")

            def close(self):
                self.closed = True

        child = FakeChild()
        fake_pexpect = types.SimpleNamespace(
            EOF=object(),
            spawn=mock.Mock(return_value=child),
        )
        with tempfile.TemporaryDirectory() as root:
            runtime = runner.prepare_runtime(make_config(Path(root)), "top")
            with mock.patch.object(runner.sys, "platform", "linux"):
                with mock.patch.dict(sys.modules, {"pexpect": fake_pexpect}):
                    with mock.patch.object(
                        runner,
                        "require_executable",
                        return_value=Path("/bin/fake"),
                    ):
                        with mock.patch.object(
                            runner.sys.stdin,
                            "isatty",
                            return_value=True,
                        ):
                            code = runner.run_pty_process(
                                "fake",
                                ["-f", "fm.tcl"],
                                runtime,
                            )

            self.assertEqual(code, 0)
            self.assertTrue(child.interacted)
            self.assertTrue(child.closed)
            self.assertEqual(child.filtered, b"fm_shell> ")
            self.assertIn("fm_shell> ", runtime.log_file.read_text(encoding="utf-8"))

    def test_list_designs_excludes_common_nested_and_invalid_filelists(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            filelist_root = root_path / "filelists"
            (filelist_root / "subdir").mkdir(parents=True)
            for relative in (
                "top.f",
                "cpu_core.f",
                "common.f",
                "bad-name.f",
                "subdir/nested.f",
            ):
                (filelist_root / relative).write_text("", encoding="utf-8")
            config = make_config(root_path)

            self.assertEqual(runner.list_designs(config), ["cpu_core", "top"])

if __name__ == "__main__":
    unittest.main()
