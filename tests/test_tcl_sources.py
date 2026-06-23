import unittest
from pathlib import Path


TCL_ROOT = Path(__file__).resolve().parents[1] / "tcl"


class TclSourceTests(unittest.TestCase):
    def test_all_tcl_files_are_syntactically_complete(self):
        try:
            import tkinter
        except ImportError:
            self.skipTest("Python Tcl runtime is unavailable")

        interpreter = tkinter.Tcl()
        files = list(TCL_ROOT.rglob("*.tcl"))
        self.assertTrue(files)
        for path in files:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertEqual(interpreter.call("info", "complete", source), 1)

    def test_shared_tcl_libraries_can_be_loaded(self):
        try:
            import tkinter
        except ImportError:
            self.skipTest("Python Tcl runtime is unavailable")

        interpreter = tkinter.Tcl()
        for relative in ("common/run_de_common.tcl", "spyglass/common.tcl"):
            path = TCL_ROOT / relative
            with self.subTest(path=relative):
                interpreter.call("source", str(path))

    def test_syn_tcl_keeps_required_common_setup(self):
        source = (TCL_ROOT / "dc" / "syn.tcl").read_text(encoding="utf-8")
        for setting in (
            "set_host_options -max_cores",
            "bus_range_separator_style",
            "bus_multiple_separator_style",
            "bus_multiple_name_separator_style",
            'synthetic_library "dw_foundation.sldb"',
            "target_library",
            "link_library",
            "define_design_lib WORK",
            "+define+",
            "if {[link]}",
            "exit 1",
            "ELAB ABORT: link failed",
            "uniquify_naming_style",
            "uniquify -force",
            "dont_use_cell_tcl",
            "dont_touch_tcl",
            "set_fix_multiple_port_nets -all -buffer_constants",
            "verilogout_no_tri",
            "set_max_area 0",
            "set_max_fanout 32 [current_design]",
            "set_max_fanout 32 [get_designs *]",
            "set_register_merging [get_designs *] false",
            "set_leakage_optimization true",
            "report_sdc_check.tcl",
            "run_de::dc_report_sdc_check",
            "report_final.tcl",
            "run_de::dc_report_final",
            "set_svf",
            "_syn.svf",
            "set_svf -off",
            "_gtech_uniq.v",
            "_gtech_uniq.ddc",
            "_syn.ddc",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, source)
        self.assertNotIn("set_black_box", source)
        self.assertNotIn("black_boxes", source)

    def test_fm_tcl_keeps_required_common_setup(self):
        source = (TCL_ROOT / "formality" / "fm.tcl").read_text(encoding="utf-8")
        self.assertLess(
            source.index("run_de::load_context"),
            source.index("set sh_command_log_file"),
        )
        for setting in (
            "synopsys_auto_setup true",
            "sh_command_log_file",
            "hdlin_verification_std 2001",
            "hdlin_while_loop_iterations 8192",
            "verification_failing_unread_limit 500",
            'verification_verify_unread_tech_cell_pins "false"',
            'hdlin_enable_1735_support "true"',
            "hdlin_sverilog_std 2017",
            "power_preserve_rtl_hier_names TRUE",
            "hdlin_enable_rtldrc_info true",
            "hdlin_library_auto_correct true",
            "svf_scan true",
            "verification_set_undriven_signals synthesis",
            "verification_clock_gate_reverse_gating true",
            "hdlin_unresolved_modules black_box",
            "set_mismatch_message_filter -warn",
            "FMR_VLOG-091",
            "FMR_ELAB-117",
            "FMR_ELAB-146",
            "FMR_ELAB-147",
            "set_host_option -max_core 8",
            "if {[llength $run_de(library_files)] > 0}",
            "set link_library $run_de(library_files)",
            "read_db $link_library",
            "fm_define_options",
            "+define+$define",
            'read_sverilog -r -vcs "-f $filelist $fm_define_options -sverilog"',
            "report_unmatch -point_type bbox",
            "unmatched_compare_points.rpt",
            "report_unmatch -status unread",
            "unmatched_unread.rpt",
            "report_unmatched_points -datapath",
            "unmatched_datapath.rpt",
            "report_matched_points -compare_rule",
            "matched_compare_points.rpt",
            "report_matched_points -compare_rule -datapath",
            "matched_datapath.rpt",
            "report_matched_points -status unread",
            "matched_unread.rpt",
            "set verify_passed [verify]",
            "save_session -replace",
            "_verify_debug.fss",
            "report_failing_points",
            "failing_points.rpt",
            "report_unverified_points",
            "unverified_points.rpt",
            "report_black_boxes",
            "black_box.rpt",
            "report_aborted_points",
            "aborted_points.rpt",
            "report_passing_points -compare_rule",
            "passing_points.rpt",
            "report_guidance -summary",
            "guidance_sum.rpt",
            "report_status",
            "status.rpt",
            "report_unread_endpoints -all -point_type reg",
            "unread.rpt",
            "exit 1",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, source)

    def test_dc_dont_use_cell_hook_contains_default_rules(self):
        source = (TCL_ROOT / "dc" / "dont_use_cell.tcl").read_text(
            encoding="utf-8"
        )
        for pattern in (
            "*/*ULVT*",
            "*/*DO*",
            "*/*BUFFD1BWP*",
            "*/*BUFFD20BWP*",
            "*/*INVD1BWP*",
            "*/*INVD20BWP*",
            "*/*DEL*",
            "*/*CK*",
            "*/*TIE*",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, source)

    def test_dc_final_report_suite_contains_required_reports(self):
        source = (TCL_ROOT / "dc" / "report_final.tcl").read_text(encoding="utf-8")
        for command in (
            "report_area -hierarchy",
            "report_timing",
            "report_clock -skew -attributes",
            "report_constraint -all_violators",
            "report_qor",
            "report_hierarchy -noleaf",
            "report_reference -hierarchy",
            "report_power -hierarchy",
            "report_clock_gating",
            "10_clock_gating.rpt",
            "report_path_group",
            "check_timing",
            "check_design",
            "13_per_clock_",
        ):
            with self.subTest(command=command):
                self.assertIn(command, source)

    def test_dc_sdc_check_report_suite_contains_required_reports(self):
        source = (TCL_ROOT / "dc" / "report_sdc_check.tcl").read_text(
            encoding="utf-8"
        )
        for command in (
            "check_design",
            "check_timing",
            "report_clock -skew -attributes",
            "report_clock -groups",
            "report_port -verbose",
            "sdc_check",
        ):
            with self.subTest(command=command):
                self.assertIn(command, source)


if __name__ == "__main__":
    unittest.main()
