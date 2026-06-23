# Shared bootstrap used by every run_de-managed Tcl flow.

namespace eval run_de {}

proc run_de::load_context {} {
    global env run_de
    if {![info exists env(RUN_DE_CONTEXT)]} {
        error "RUN_DE_CONTEXT is not set"
    }
    if {![file isfile $env(RUN_DE_CONTEXT)]} {
        error "run_de context not found: $env(RUN_DE_CONTEXT)"
    }
    source $env(RUN_DE_CONTEXT)

    foreach key {flow design work_dir report_dir output_dir filelists} {
        if {![info exists run_de($key)]} {
            error "run_de context is missing '$key'"
        }
    }
}

proc run_de::optional_source {path description} {
    if {$path eq ""} {
        puts "No $description configured; skipping."
        return
    }
    if {![file isfile $path]} {
        error "$description not found: $path"
    }
    puts "Loading $description: $path"
    uplevel #0 [list source $path]
}

proc run_de::finish {{exit_code 0}} {
    global run_de
    # SpyGlass -shell remains interactive after a Tcl file reaches EOF. Batch
    # flows must exit explicitly; GUI flows intentionally keep the tool alive.
    if {![info exists run_de(gui)] || $run_de(gui) ne "1"} {
        puts "run_de batch flow completed; exiting tool shell with code $exit_code."
        exit $exit_code
    }
}
