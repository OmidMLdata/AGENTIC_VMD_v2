# vmd-agent live bridge: lets vmd-agent drive THIS VMD window, and nothing else can.
#
# How it stays safe:
#   * It listens on 127.0.0.1 only, and a request must start with the one-time token that vmd-agent generated for this session.
#   * A request is a Tcl *list* `token id verb arg ...`. It is only ever taken apart with list commands: it is never eval'd,
#     subst'd or expr'd, so text inside an argument ("[exit]", "$x", ";") is just text.
#   * `verb` must be one of the names in ::vmdagent_link::verbs, and runs the procedure ::vmdagent_link::v_<verb>.
#     Each procedure checks every argument again (numbers, molecule ids, files, choices from fixed lists, a selection restricted
#     to the characters VMD's selection language needs) and then calls VMD's own commands with the values as separate words.
#   * There is no verb that runs Tcl, executes a program or reads a file; `quit` is not one of them.
# Replies are one line of JSON: {"id":N,"ok":true,"result":...} or {"id":N,"ok":false,"error":"..."}.

namespace eval ::vmdagent_link {
    variable token "@TOKEN@"
    variable port @PORT@
    variable headless @HEADLESS@
    variable styles {@STYLES@}
    variable colors {@COLORS@}
    variable materials {@MATERIALS@}
    variable filetypes {@FILETYPES@}
    variable bgcolors {@BGCOLORS@}
    variable axeslocs {Off LowerLeft LowerRight UpperLeft UpperRight Origin}
    variable verbs {ping state mol_list mol_new mol_addfile mol_delete mol_top mol_rename mol_show mol_clear
                    rep_list rep_add rep_modify rep_delete display view anim query measure label_add label_clear
                    snapshot save_state}
    variable tracked
    array set tracked {projection Perspective axes LowerLeft background black shadows off ambientocclusion off culling off antialias off}
    variable savedviews
    array set savedviews {}
    variable server ""
    variable maxatoms 50
}

# ---- JSON out
proc ::vmdagent_link::js {s} {
    set s [string map [list "\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "\\r" "\t" "\\t"] $s]
    return "\"$s\""
}
proc ::vmdagent_link::jn {x} {
    if {[string is double -strict $x] && ![string match -nocase "*n*" $x]} { return $x }
    return [js $x]
}
proc ::vmdagent_link::jb {x} { return [expr {$x ? "true" : "false"}] }
proc ::vmdagent_link::jarr {items} { return "\[[join $items ,]\]" }
proc ::vmdagent_link::jobj {args} {
    set parts {}
    foreach {k v} $args { lappend parts "[js $k]:$v" }
    return "{[join $parts ,]}"
}

# ---- argument checks (every verb repeats them: nothing is trusted because Python already looked)
proc ::vmdagent_link::need_int {x what} {
    if {![string is integer -strict $x]} { error "$what must be a whole number" }
    return $x
}
proc ::vmdagent_link::need_num {x what} {
    if {![string is double -strict $x] || [string match -nocase "*n*" $x]} { error "$what must be a number" }
    return $x
}
proc ::vmdagent_link::need_in {x choices what} {
    if {[lsearch -exact $choices $x] < 0} { error "$what must be one of: [join $choices {, }]" }
    return $x
}
proc ::vmdagent_link::need_onoff {x what} { return [need_in $x {on off} $what] }
proc ::vmdagent_link::need_sel {x} {
    if {![regexp {^[A-Za-z0-9_ ()+\-.'*:,<>=]+$} $x]} { error "the selection has characters that are not allowed" }
    if {[string length [string trim $x]] == 0} { error "the selection is empty" }
    return $x
}
proc ::vmdagent_link::need_path {x} {
    if {![regexp {^(/|[A-Za-z]:/)} $x]} { error "the file name must be an absolute path" }
    if {[regexp {[\x00-\x1f\x7f\{\}\\]} $x]} { error "the path has a character that is not allowed" }
    return $x
}
proc ::vmdagent_link::need_mol {x} {
    need_int $x "molecule"
    if {[lsearch -exact [molinfo list] $x] < 0} { error "there is no molecule $x" }
    return $x
}
proc ::vmdagent_link::need_rep {m i} {
    need_int $i "representation"
    if {$i < 0 || $i >= [molinfo $m get numreps]} { error "molecule $m has no representation $i" }
    return $i
}
# VMD accepts a text it cannot parse as a representation's selection and draws nothing; asking atomselect first turns that into an error that says so
proc ::vmdagent_link::check_selection {m sel} {
    if {[catch {atomselect $m $sel} s]} { error "VMD cannot read that selection: $s" }
    $s delete
    return $sel
}
proc ::vmdagent_link::need_color {x} {
    variable colors
    if {[regexp {^ColorID [0-9]+$} $x]} { return $x }
    return [need_in $x $colors "color"]
}
proc ::vmdagent_link::need_style {x} {
    variable styles
    return [need_in $x $styles "style"]
}
proc ::vmdagent_link::need_params {params} {
    set out {}
    foreach p $params { lappend out [need_num $p "a style parameter"] }
    if {[llength $out] > 8} { error "too many style parameters" }
    return $out
}
proc ::vmdagent_link::top_mol {} {
    if {[molinfo num] == 0} { error "no molecule is loaded" }
    return [molinfo top]
}

# ---- molecules
proc ::vmdagent_link::mol_obj {m top} {
    set file [lindex [molinfo $m get filename] 0]
    return [jobj id $m name [js [molinfo $m get name]] natoms [molinfo $m get numatoms] nframes [molinfo $m get numframes] \
        frame [molinfo $m get frame] top [jb [expr {$m == $top}]] shown [jb [molinfo $m get drawn]] active [jb [molinfo $m get active]] \
        numreps [molinfo $m get numreps] file [js $file]]
}
proc ::vmdagent_link::rep_obj {m i} {
    return [jobj index $i style [js [lindex [molinfo $m get [list [list rep $i]]] 0]] selection [js [lindex [molinfo $m get [list [list selection $i]]] 0]] \
        color [js [lindex [molinfo $m get [list [list color $i]]] 0]] material [js [lindex [molinfo $m get [list [list material $i]]] 0]] \
        shown [jb [mol showrep $m $i]]]
}
proc ::vmdagent_link::v_ping {} {
    variable headless
    return [jobj vmd [js [vmdinfo version]] headless [jb $headless] molecules [molinfo num]]
}
proc ::vmdagent_link::v_mol_list {} {
    set top [expr {[molinfo num] > 0 ? [molinfo top] : -1}]
    set out {}
    foreach m [molinfo list] { lappend out [mol_obj $m $top] }
    return [jarr $out]
}
proc ::vmdagent_link::v_state {} {
    variable tracked
    variable headless
    set top [expr {[molinfo num] > 0 ? [molinfo top] : -1}]
    set mols {}
    foreach m [molinfo list] {
        set reps {}
        for {set i 0} {$i < [molinfo $m get numreps]} {incr i} { lappend reps [rep_obj $m $i] }
        lappend mols [string range [mol_obj $m $top] 0 end-1],"reps":[jarr $reps]\}
    }
    set disp {}
    foreach k [lsort [array names tracked]] { lappend disp $k [js $tracked($k)] }
    lappend disp depthcue [jb [display get depthcue]]
    return [jobj vmd [js [vmdinfo version]] headless [jb $headless] top $top molecules [jarr $mols] display [jobj {*}$disp]]
}
proc ::vmdagent_link::v_mol_new {path type} {
    variable filetypes
    need_path $path
    if {$type ne ""} { need_in $type $filetypes "file type" }
    if {$type eq ""} { set id [mol new $path waitfor all] } else { set id [mol new $path type $type waitfor all] }
    if {$id < 0 || [lsearch -exact [molinfo list] $id] < 0} { error "VMD could not read $path" }
    return [jobj id $id natoms [molinfo $id get numatoms] nframes [molinfo $id get numframes]]
}
proc ::vmdagent_link::v_mol_addfile {m path type dropfirst} {
    variable filetypes
    need_mol $m
    need_path $path
    need_in $type $filetypes "file type"
    set before [molinfo $m get numframes]
    mol addfile $path type $type waitfor all $m
    if {$dropfirst eq "1" && $before > 0} { animate delete beg 0 end 0 $m }
    return [jobj id $m natoms [molinfo $m get numatoms] nframes [molinfo $m get numframes]]
}
proc ::vmdagent_link::v_mol_delete {m} { need_mol $m; mol delete $m; return [jobj deleted $m] }
proc ::vmdagent_link::v_mol_top {m} { need_mol $m; mol top $m; return [jobj top $m] }
proc ::vmdagent_link::v_mol_rename {m name} {
    need_mol $m
    if {![regexp {^[A-Za-z0-9_. -]{1,60}$} $name]} { error "a name has letters, digits, spaces and . _ - only" }
    mol rename $m $name
    return [jobj id $m name [js $name]]
}
proc ::vmdagent_link::v_mol_show {m onoff} {
    need_mol $m
    need_onoff $onoff "show"
    mol $onoff $m
    return [jobj id $m shown [jb [expr {$onoff eq "on"}]]]
}
proc ::vmdagent_link::v_mol_clear {} {
    set n 0
    foreach m [molinfo list] { mol delete $m; incr n }
    return [jobj deleted $n]
}

# ---- representations
proc ::vmdagent_link::v_rep_list {m} {
    need_mol $m
    set out {}
    for {set i 0} {$i < [molinfo $m get numreps]} {incr i} { lappend out [rep_obj $m $i] }
    return [jarr $out]
}
proc ::vmdagent_link::v_rep_add {m sel style color material args} {
    variable materials
    need_mol $m
    need_sel $sel
    check_selection $m $sel
    need_style $style
    need_color $color
    need_in $material $materials "material"
    set params [need_params $args]
    mol selection $sel
    mol representation $style {*}$params
    mol color {*}$color
    mol material $material
    mol addrep $m
    return [jobj index [expr {[molinfo $m get numreps] - 1}]]
}
proc ::vmdagent_link::v_rep_modify {m i key value args} {
    variable materials
    need_mol $m
    need_rep $m $i
    switch -exact -- $key {
        selection { mol modselect $i $m [check_selection $m [need_sel $value]] }
        style     { mol modstyle $i $m [need_style $value] {*}[need_params $args] }
        color     { mol modcolor $i $m {*}[need_color $value] }
        material  { mol modmaterial $i $m [need_in $value $materials "material"] }
        show      { mol showrep $m $i [need_onoff $value "show"] }
        default   { error "key must be one of: selection, style, color, material, show" }
    }
    return [rep_obj $m $i]
}
proc ::vmdagent_link::v_rep_delete {m i} {
    need_mol $m
    need_rep $m $i
    mol delrep $i $m
    return [jobj deleted $i remaining [molinfo $m get numreps]]
}

# ---- display and view
proc ::vmdagent_link::v_display {key value} {
    variable tracked
    variable bgcolors
    variable axeslocs
    switch -exact -- $key {
        projection { display projection [need_in $value {Perspective Orthographic} "projection"]; set tracked(projection) $value }
        depthcue   { display depthcue [need_onoff $value "depthcue"] }
        cuestart   { display cuestart [need_num $value "cuestart"] }
        cueend     { display cueend [need_num $value "cueend"] }
        cuedensity { display cuedensity [need_num $value "cuedensity"] }
        background { color Display Background [need_in $value $bgcolors "background"]; set tracked(background) $value }
        axes       { axes location [need_in $value $axeslocs "axes location"]; set tracked(axes) $value }
        shadows    { display shadows [need_onoff $value "shadows"]; set tracked(shadows) $value }
        ambientocclusion { display ambientocclusion [need_onoff $value "ambient occlusion"]; set tracked(ambientocclusion) $value }
        aoambient  { display aoambient [need_num $value "aoambient"] }
        aodirect   { display aodirect [need_num $value "aodirect"] }
        culling    { display culling [need_onoff $value "culling"]; set tracked(culling) $value }
        antialias  { display antialias [need_onoff $value "antialias"]; set tracked(antialias) $value }
        default    { error "unknown display setting" }
    }
    display update
    return [jobj setting [js $key] value [js $value]]
}
proc ::vmdagent_link::v_view {kind args} {
    variable savedviews
    switch -exact -- $kind {
        reset  { display resetview }
        rotate {
            lassign $args axis deg
            need_in $axis {x y z} "axis"
            rotate $axis by [need_num $deg "degrees"]
        }
        scale {
            lassign $args f
            if {[need_num $f "factor"] <= 0} { error "the factor must be positive" }
            scale by $f
        }
        translate {
            lassign $args x y z
            translate by [need_num $x "x"] [need_num $y "y"] [need_num $z "z"]
        }
        center {
            lassign $args sel m
            need_mol $m
            set s [atomselect $m [need_sel $sel]]
            if {[$s num] == 0} { $s delete; error "the selection matches no atoms" }
            set c [measure center $s]
            $s delete
            foreach mm [molinfo list] { molinfo $mm set center_matrix [list [transoffset [vecscale -1.0 $c]]] }
        }
        save {
            lassign $args name
            if {![regexp {^[A-Za-z0-9_-]{1,30}$} $name]} { error "a view name has letters, digits, _ and - only" }
            set m [top_mol]
            set savedviews($name) [list [molinfo $m get center_matrix] [molinfo $m get rotate_matrix] [molinfo $m get scale_matrix] [molinfo $m get global_matrix]]
        }
        restore {
            lassign $args name
            if {![info exists savedviews($name)]} { error "no saved view called $name" }
            lassign $savedviews($name) c r s g
            foreach mm [molinfo list] {
                molinfo $mm set center_matrix $c; molinfo $mm set rotate_matrix $r; molinfo $mm set scale_matrix $s; molinfo $mm set global_matrix $g
            }
        }
        default { error "view must be one of: reset, rotate, scale, translate, center, save, restore" }
    }
    display update
    return [jobj view [js $kind]]
}

# ---- animation
proc ::vmdagent_link::v_anim {kind args} {
    set m [top_mol]
    set n [molinfo $m get numframes]
    switch -exact -- $kind {
        goto {
            lassign $args f
            need_int $f "frame"
            if {$f < 0 || $f >= $n} { error "the frame must be from 0 to [expr {$n - 1}]" }
            animate goto $f
        }
        forward - reverse - pause { animate $kind }
        style { lassign $args s; animate style [string totitle [need_in $s {once loop rock} "animation style"]] }
        speed { lassign $args v; if {[need_num $v "speed"] < 0 || $v > 1} { error "speed is from 0 to 1" }; animate speed $v }
        skip  { lassign $args k; if {[need_int $k "skip"] < 1} { error "skip is 1 or more" }; animate skip $k }
        default { error "animate must be one of: goto, forward, reverse, pause, style, speed, skip" }
    }
    return [jobj molecule $m frame [molinfo $m get frame] nframes $n]
}

# ---- asking VMD things
proc ::vmdagent_link::v_query {sel m} {
    need_mol $m
    set s [atomselect $m [need_sel $sel]]
    set n [$s num]
    if {$n == 0} { $s delete; return [jobj natoms 0] }
    set resn {}
    foreach r [$s get resname] { if {[info exists cnt($r)]} { incr cnt($r) } else { set cnt($r) 1 } }
    foreach r [lrange [lsort [array names cnt]] 0 19] { lappend resn [jobj name [js $r] atoms $cnt($r)] }
    set res [llength [lsort -unique [$s get residue]]]
    set chains [lsort -unique [$s get chain]]
    set c [measure center $s]
    set mm [measure minmax $s]
    set out [jobj natoms $n residues $res chains [jarr [lmap x $chains {js $x}]] resnames [jarr $resn] \
        center [jarr [lmap x $c {jn $x}]] min [jarr [lmap x [lindex $mm 0] {jn $x}]] max [jarr [lmap x [lindex $mm 1] {jn $x}]] \
        rgyr [jn [measure rgyr $s weight mass]] frame [molinfo $m get frame]]
    $s delete
    return $out
}
proc ::vmdagent_link::v_measure {kind m args} {
    need_mol $m
    set idx {}
    switch -exact -- $kind {
        bond     { set k 2 }
        angle    { set k 3 }
        dihedral { set k 4 }
        sasa     { lassign $args radius sel; need_num $radius "probe radius"
                   set s [atomselect $m [need_sel $sel]]
                   set v [measure sasa $radius $s]; $s delete
                   return [jobj kind [js sasa] value [jn $v] unit [js "A^2"]] }
        default  { error "measure must be one of: bond, angle, dihedral, sasa" }
    }
    if {[llength $args] != $k} { error "$kind needs $k atom indices" }
    foreach a $args { lappend idx [need_int $a "an atom index"] }
    set v [measure $kind $idx molid $m]
    return [jobj kind [js $kind] value [jn $v] frame [molinfo $m get frame]]
}
proc ::vmdagent_link::v_label_add {sel m limit} {
    variable maxatoms
    need_mol $m
    need_int $limit "limit"
    if {$limit < 1 || $limit > $maxatoms} { set limit $maxatoms }
    set s [atomselect $m [need_sel $sel]]
    set ids [lrange [$s list] 0 [expr {$limit - 1}]]
    $s delete
    foreach i $ids { label add Atoms $m/$i }
    return [jobj labelled [llength $ids]]
}
proc ::vmdagent_link::v_label_clear {} { label delete Atoms all; return [jobj cleared true] }

# ---- pictures and state files
proc ::vmdagent_link::v_snapshot {path quality} {
    variable headless
    need_path $path
    need_in $quality {fast tachyon} "quality"
    file delete -force $path
    if {$quality eq "fast" && !$headless} { render snapshot $path } else { render TachyonInternal $path }
    if {![file exists $path]} { error "VMD did not write the picture" }
    return [jobj path [js $path] bytes [file size $path] renderer [js [expr {$quality eq "fast" && !$headless ? "snapshot" : "TachyonInternal"}]]]
}
proc ::vmdagent_link::v_save_state {path} {
    need_path $path
    save_state $path
    return [jobj path [js $path]]
}

# ---- the listener
proc ::vmdagent_link::reply {chan id ok payload} {
    if {$ok} { set line "{[js id]:$id,[js ok]:true,[js result]:$payload}" } else { set line "{[js id]:$id,[js ok]:false,[js error]:$payload}" }
    catch { puts $chan $line; flush $chan }
}
proc ::vmdagent_link::handle {chan line} {
    variable token
    variable verbs
    if {[catch {llength $line} n] || $n < 3} { reply $chan 0 0 [js "malformed request"]; return }
    lassign $line tok id verb
    if {![string equal $tok $token]} { catch {close $chan}; return }
    if {![string is integer -strict $id]} { set id 0 }
    if {[lsearch -exact $verbs $verb] < 0} { reply $chan $id 0 [js "unknown verb"]; return }
    if {[catch {v_$verb {*}[lrange $line 3 end]} res]} {
        reply $chan $id 0 [js $res]
    } else {
        reply $chan $id 1 $res
    }
}
proc ::vmdagent_link::readable {chan} {
    if {[catch {gets $chan line} n] || [eof $chan]} { catch {close $chan}; return }
    if {$n < 0} { return }
    if {$n > 100000} { reply $chan 0 0 [js "request too long"]; return }
    handle $chan $line
}
proc ::vmdagent_link::accept {chan addr port} {
    if {$addr ne "127.0.0.1"} { catch {close $chan}; return }
    fconfigure $chan -buffering line -translation lf -encoding utf-8 -blocking 0
    fileevent $chan readable [list ::vmdagent_link::readable $chan]
}
proc ::vmdagent_link::start {} {
    variable server
    variable port
    if {$server ne ""} { return }
    set server [socket -server ::vmdagent_link::accept -myaddr 127.0.0.1 $port]
    puts "Info) vmd-agent bridge: listening on 127.0.0.1:$port"
}
::vmdagent_link::start
