# Formality entry point.
# Reference/implementation library setup is project-specific and should be
# maintained by the design team in this file.
set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir .. common run_de_common.tcl]
run_de::load_context

puts "Starting Formality for $run_de(design)"
set PRJ_CODE $env(PRJ_CODE)
set sh_command_log_file [file join $run_de(work_dir) fm_shell_command.log]

# Default Formality setup shared by all run_de FM checks.
set synopsys_auto_setup true

# set hdlin_unresolved_modules black_box
# set hdlin_error_on_mismatch_message false
# set verification_failing_point_limit 1000
# set verification_set_undriven_signals 0:X
# set hdlin_ignore_full_case false
# set hdlin_ignore_parallel_case false
# set verification_directly_unriven_output true
# set verification_clock_gate_edge_analysis true


# User setting
# hdlin/verification
set hdlin_verification_std 2001
set hdlin_while_loop_iterations 8192
set verification_failing_unread_limit 500
set verification_verify_unread_tech_cell_pins "false"
set hdlin_enable_1735_support "true"
# set_app_var hdlin_enable_link_error_verbose "true"
set hdlin_sverilog_std "2012"
set hdlin_sverilog_std 2017
# set_app_var verification_binary_constraint_propagation true
# set_app_var verification_assume_reg_init auto

set power_preserve_rtl_hier_names TRUE
set hdlin_enable_rtldrc_info true

# set bus_naming_style %s_%d
set hdlin_library_auto_correct true
set svf_scan true

set verification_set_undriven_signals 0
set verification_set_undriven_signals synthesis
# set verification_clock_gate_hold_mode collapse_all_cg_cells
set verification_clock_gate_reverse_gating true
set hdlin_unresolved_modules black_box

# Reduce selected mismatches to warning.
set_mismatch_message_filter -warn [list FMR_VLOG-091 FMR_ELAB-117 FMR_ELAB-146 FMR_ELAB-147]
# set_mismatch_message_filter -warn [list FMR_VLOG-100]
# set_mismatch_message_filter -warn [list FMR_VLOG-029]

# Host cores
set_host_option -max_core 8

if {[llength $run_de(library_files)] > 0} {
    set link_library $run_de(library_files)
    puts "Reading Formality libraries: $link_library"
    read_db $link_library
}


if {[info exists run_de(svf_file)] && $run_de(svf_file) ne ""} {
    puts "Reading Formality SVF: $run_de(svf_file)"
    set_svf $run_de(svf_file)
}


# Reference RTL is provided through run_de(filelists). Add project-specific
# read_sverilog/read_db commands here, then load the synthesized implementation.
set fm_define_options ""
foreach define $run_de(defines) {
    append fm_define_options " +define+$define"
}

foreach filelist $run_de(filelists) {
    read_sverilog -r -vcs "-f $filelist $fm_define_options -sverilog"
}
set_top r:/WORK/$run_de(design)

if {[info exists run_de(impl_netlist)] && $run_de(impl_netlist) ne ""} {
    set impl_netlist $run_de(impl_netlist)
} elseif {[info exists env(RUN_DE_IMPL_NETLIST)]} {
    set impl_netlist $env(RUN_DE_IMPL_NETLIST)
} else {
    error "Implementation netlist is required; use fm -time or RUN_DE_IMPL_NETLIST"
}
puts "Reading Formality implementation netlist: $impl_netlist"
read_verilog -i $impl_netlist
set_top i:/WORK/$run_de(design)

foreach black_box $run_de(black_boxes) {
    foreach container {r i} {
        set design_id "${container}:/WORK/${black_box}"
        if {[catch {set_black_box $design_id} black_box_error]} {
            puts "Warning: cannot set Formality black box $design_id: $black_box_error"
        } else {
            puts "Setting Formality black box: $design_id"
        }
    }
}

match

report_unmatch -point_type bbox \
    > [file join $run_de(report_dir) unmatched_compare_points.rpt]
report_unmatch -status unread \
    > [file join $run_de(report_dir) unmatched_unread.rpt]
report_unmatched_points -datapath \
    > [file join $run_de(report_dir) unmatched_datapath.rpt]
report_matched_points -compare_rule \
    > [file join $run_de(report_dir) matched_compare_points.rpt]
report_matched_points -compare_rule -datapath \
    > [file join $run_de(report_dir) matched_datapath.rpt]
report_matched_points -status unread \
    > [file join $run_de(report_dir) matched_unread.rpt]

set verify_passed [verify]
if {!$verify_passed} {
    save_session -replace \
        [file join $run_de(output_dir) "$run_de(design)_verify_debug.fss"]
}

report_failing_points \
    > [file join $run_de(report_dir) failing_points.rpt]
report_unverified_points \
    > [file join $run_de(report_dir) unverified_points.rpt]
report_black_boxes \
    > [file join $run_de(report_dir) black_box.rpt]
report_aborted_points \
    > [file join $run_de(report_dir) aborted_points.rpt]
report_passing_points -compare_rule \
    > [file join $run_de(report_dir) passing_points.rpt]
report_guidance -summary \
    > [file join $run_de(report_dir) guidance_sum.rpt]
report_status \
    > [file join $run_de(report_dir) status.rpt]
report_unread_endpoints -all -point_type reg \
    > [file join $run_de(report_dir) unread.rpt]

#if {!$verify_passed} {
#    puts stderr "Formality verification failed for $run_de(design)"
#    exit 1
#}

puts "Formality completed for $run_de(design)"
