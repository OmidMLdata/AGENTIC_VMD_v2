mol new structure.psf type psf waitfor all
mol addfile prod.dcd type dcd waitfor all
set n [molinfo top get numframes]
set o [open careful_raw.txt w]; puts $o "NFRAMES $n"
set ref [atomselect top "protein and name CA" frame 0]
set cmp [atomselect top "protein and name CA"]
set allp [atomselect top all]
for {set f 0} {$f < $n} {incr f} { $cmp frame $f; $allp frame $f; $allp move [measure fit $cmp $ref]; puts $o "RMSD $f [measure rmsd $cmp $ref]" }
foreach r [$cmp get resid] v [measure rmsf $cmp first 0 last -1 step 1] { puts $o "RMSF $r $v" }
close $o; quit
