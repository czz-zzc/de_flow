# Shared SpyGlass implementation. lint.tcl and cdc.tcl own their goal lists.

namespace eval run_de_spyglass {}

proc run_de_spyglass::goal_report_dir {goal} {
    global run_de
    set goal_label [file tail $goal]
    regsub -all {[^A-Za-z0-9_.-]} $goal_label "_" goal_label
    return [file join $run_de(report_dir) $goal_label]
}

proc run_de_spyglass::write_reports {goal} {
    global run_de
    set report_dir [run_de_spyglass::goal_report_dir $goal]
    file mkdir $report_dir
    puts "Writing SpyGlass reports for goal $goal: $report_dir"
    foreach report_type {
        goal_setup summary waiver moresimple simple spyglass_violations
        stop_summary ignore_summary
    } {
        set report_file [file join \
            $report_dir "$run_de(design)_${report_type}.rpt"]
        write_report $report_type > $report_file
    }
}

proc run_de_spyglass::run {kind goals} {
    global env run_de

    puts "Starting SpyGlass $kind for $run_de(design)"
    new_project $run_de(design) -projectwdir $run_de(work_dir) -force
    current_project

    set_option language_mode mixed
    set_option mthresh 800000
    set_option enableSV09 yes
    set_option enable_save_restore 0
    set_option prefer_tech_lib yes
    set_option dw yes
    set_option show_lib yes

    if {$kind eq "cdc"} {
        set_option sdc2sgdc yes
        set_parameter enable_generated_clocks yes
        set_parameter use_inferred_clocks yes
    }

    foreach define $run_de(defines) {
        set_option define $define
    }
    foreach filelist $run_de(filelists) {
        read_file -type sourcelist $filelist
    }
    foreach library_file $run_de(library_files) {
        puts "Reading SpyGlass library: $library_file"
        read_file -type gateslib $library_file
    }

    if {$kind eq "cdc"} {
        if {$run_de(sdc_file) eq ""} {
            puts "No SDC file found; CDC will run without constraints."
        } else {
            current_design $run_de(design)
            sdc_data -file $run_de(sdc_file)
        }
    }

    foreach module $run_de(black_boxes) {
        set_option stop $module
    }

    set_option top $run_de(design)
    current_goal Design_Read -top $run_de(design)
    link_design -force

    current_methodology $env(SPYGLASS_HOME)/GuideWare/latest/block/rtl_handoff
    run_de::optional_source $run_de(custom_policy_file) "custom policy"

    if {$run_de(waiver_file) ne ""} {
        read_file -type awl $run_de(waiver_file)
    }

    foreach goal $goals {
        puts "Running goal: $goal"
        current_goal $goal -top $run_de(design)
        if {$kind eq "lint"} {
            set_parameter handle_large_bus yes
        }
        run_goal
        run_de_spyglass::write_reports $goal
    }

    save_project
    puts "SpyGlass $kind completed for $run_de(design)"
}
