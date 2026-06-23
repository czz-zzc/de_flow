import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from deflow.config import ConfigError, load_config


PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "run_de_config.yaml"


class ConfigTests(unittest.TestCase):
    def test_missing_project_root_is_fatal(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigError, "PROJ_ROOT"):
                load_config("compile", str(PROJECT_CONFIG))

    def test_configuration_expands_external_and_internal_variables(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"PROJ_ROOT": root}, clear=True):
                config = load_config("lint", str(PROJECT_CONFIG))

        self.assertNotIn("${PROJ_ROOT}", config.flow["work_path"])
        self.assertTrue(config.flow["script"].endswith("tcl/spyglass/lint.tcl"))

    def test_only_selected_flow_is_validated_and_expanded(self):
        raw = yaml.safe_load(PROJECT_CONFIG.read_text(encoding="utf-8"))
        broken = copy.deepcopy(raw)
        del broken["flows"]["cdc"]["script"]
        broken["flows"]["cdc"]["work_path"] = "${UNUSED_CDC_ROOT}/work"

        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.yaml"
            path.write_text(yaml.safe_dump(broken), encoding="utf-8")
            with mock.patch.dict(os.environ, {"PROJ_ROOT": root}, clear=True):
                config = load_config("compile", str(path))
                self.assertEqual(config.flow_name, "compile")
                with self.assertRaises(ConfigError):
                    load_config("cdc", str(path))

    def test_project_only_load_ignores_all_flow_configuration(self):
        raw = yaml.safe_load(PROJECT_CONFIG.read_text(encoding="utf-8"))
        raw["flows"]["compile"]["work_path"] = "${UNUSED_FLOW_ROOT}/work"
        del raw["tools"]["vcs"]

        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.yaml"
            path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            with mock.patch.dict(os.environ, {"PROJ_ROOT": root}, clear=True):
                config = load_config(None, str(path))

        self.assertIsNone(config.flow_name)


if __name__ == "__main__":
    unittest.main()
