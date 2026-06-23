# Final Design Compiler report suite.
#
# This file intentionally contains report generation only. The synthesis flow
# remains in syn.tcl; this script just writes post-compile reports into
# reports/final/.

namespace eval run_de {}

proc run_de::report_section {index title detail} {
    puts "########################################################################"
    puts "# $index. $title"
    puts "# Check: $detail"
    puts "########################################################################"
}

proc run_de::sanitize_filename {value} {
    set result $value
    regsub -all {[^A-Za-z0-9_.-]} $result "_" result
    if {$result eq ""} {
        return "unnamed"
    }
    return $result
}

proc run_de::dc_report_final {} {
    global run_de

    set final_report_dir [file join $run_de(report_dir) final]
    file mkdir $final_report_dir

    run_de::report_section 1 "Area Report" \
        "Cell counts, area breakdown by hierarchy, design size"
    report_area -hierarchy > [file join $final_report_dir 1_area.rpt]

    run_de::report_section 2 "Timing Report - Setup" \
        "Worst negative slack (WNS), total negative slack (TNS)"
    report_timing \
        -delay_type max \
        -max_paths 100 \
        -nworst 1 \
        -path_type full_clock_expanded \
        -sort_by slack \
        > [file join $final_report_dir 2_timing_setup.rpt]

    run_de::report_section 3 "Timing Report - Hold" \
        "Worst hold paths"
    report_timing \
        -delay_type min \
        -max_paths 100 \
        -nworst 1 \
        -path_type full_clock_expanded \
        -sort_by slack \
        > [file join $final_report_dir 3_timing_hold.rpt]

    run_de::report_section 4 "Clock Report" \
        "All clocks are properly defined and generated"
    report_clock -skew -attributes > [file join $final_report_dir 4_clocks.rpt]

    run_de::report_section 5 "Constraint Coverage" \
        "Timing constraints completeness"
    report_constraint -all_violators > [file join $final_report_dir 5_constraints.rpt]

    run_de::report_section 6 "Quality of Results (QoR)" \
        "Overall synthesis quality summary"
    report_qor > [file join $final_report_dir 6_qor.rpt]

    run_de::report_section 7 "Design Hierarchy and Instance Count" \
        "Design structure, module instances"
    report_hierarchy -noleaf > [file join $final_report_dir 7_hierarchy.rpt]

    run_de::report_section 8 "Cell Instance Report" \
        "Standard cell usage, leaf cell distribution"
    report_reference -hierarchy > [file join $final_report_dir 8_cell_instances.rpt]

    run_de::report_section 9 "Power Report" \
        "Power consumption estimates"
    if {[llength [info commands report_power]] != 0} {
        report_power -hierarchy > [file join $final_report_dir 9_power.rpt]
    } else {
        puts "Warning: report_power command is not available; skipping power report."
    }

    run_de::report_section 10 "Clock Gating Report" \
        "Clock-gating cells, structure, and optimization summary"
    set clock_gating_report [file join $final_report_dir 10_clock_gating.rpt]
    if {[llength [info commands report_clock_gating]] != 0} {
        report_clock_gating > $clock_gating_report
    } else {
        set fh [open $clock_gating_report w]
        puts $fh "report_clock_gating command is not available in this tool."
        close $fh
        puts "Warning: report_clock_gating command is not available; wrote placeholder report."
    }

    run_de::report_section 11 "Clock Group Report" \
        "Synchronous/asynchronous clock group relationships"
    report_clock -groups > [file join $final_report_dir 11_clock_groups.rpt]

    run_de::report_section 12 "Path Group Summary" \
        "Timing summary by path groups"
    report_path_group > [file join $final_report_dir 12_path_groups.rpt]

    run_de::report_section 13 "Per-Clock Worst Path Report" \
        "Worst setup/hold paths for each clock domain individually"
    set all_clocks [get_clocks -quiet *]
    if {[sizeof_collection $all_clocks] > 0} {
        foreach_in_collection clk $all_clocks {
            set clk_name [get_object_name $clk]
            set report_clk_name [run_de::sanitize_filename $clk_name]
            puts "Generating worst path reports for clock: $clk_name"

            report_timing \
                -to [get_clocks $clk_name] \
                -delay_type max \
                -max_paths 100 \
                -nworst 1 \
                -path_type full_clock_expanded \
                -sort_by slack \
                > [file join $final_report_dir "13_per_clock_${report_clk_name}_setup.rpt"]

            report_timing \
                -to [get_clocks $clk_name] \
                -delay_type min \
                -max_paths 10 \
                -nworst 1 \
                -path_type full_clock_expanded \
                -sort_by slack \
                > [file join $final_report_dir "13_per_clock_${report_clk_name}_hold.rpt"]
        }
    } else {
        puts "Warning: No clocks found in design. Skipping per-clock reports."
    }

    run_de::report_section 14 "Check Timing Summary" \
        "Quick overview of unconstrained paths, loops, etc."
    check_timing > [file join $final_report_dir 14_check_timing.rpt]

    run_de::report_section 15 "Check Design Summary" \
        "Structural design checks"
    check_design > [file join $final_report_dir 15_check_design.rpt]
}
