# Post-SDC, pre-compile Design Compiler sanity reports.
#
# This report suite runs immediately after the design SDC and optional
# constraint_post.tcl are sourced. It captures whether constraints were loaded
# as intended before compile_ultra changes the design.

namespace eval run_de {}

proc run_de::dc_report_sdc_check {} {
    global run_de

    set sdc_check_dir [file join $run_de(report_dir) sdc_check]
    file mkdir $sdc_check_dir

    puts "SDC CHECK: check_design"
    check_design > [file join $sdc_check_dir 0_check_design.rpt]

    puts "SDC CHECK: check_timing"
    check_timing > [file join $sdc_check_dir 1_check_timing.rpt]

    puts "SDC CHECK: report_clock"
    report_clock -skew -attributes > [file join $sdc_check_dir 2_clocks.rpt]

    puts "SDC CHECK: report_clock -groups"
    report_clock -groups > [file join $sdc_check_dir 3_clock_groups.rpt]

    puts "SDC CHECK: report_port"
    report_port -verbose > [file join $sdc_check_dir 4_ports.rpt]
}
