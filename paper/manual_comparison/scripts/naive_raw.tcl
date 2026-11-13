mol new structure.psf type psf waitfor all
mol addfile prod.dcd type dcd waitfor all
set n [molinfo top get numframes]
set o [open naive_raw.txt w]; puts $o "NFRAMES $n"
set ref [atomselect top "protein and name CA" frame 0]
set cmp [atomselect top "protein and name CA"]
for {set f 0} {$f < $n} {incr f} { $cmp frame $f; puts $o "RMSD_NOFIT $f [measure rmsd $cmp $ref]" }
foreach r [$cmp get resid] v [measure rmsf $cmp first 0 last -1 step 1] { puts $o "RMSF_NOFIT $r $v" }
close $o; quit
