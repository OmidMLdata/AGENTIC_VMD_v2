mol new protein.pdb type pdb waitfor all
mol addfile protein.dcd type dcd waitfor all          ;# pitfall 1: PDB coordinates stay as frame 0
set n [molinfo top get numframes]
set o [open naive_out.txt w]
puts $o "NFRAMES $n"
set cmp [atomselect top "name CA"]
foreach r [$cmp get resid] v [measure rmsf $cmp first 0 last -1 step 1] { puts $o "RMSF_NOFIT $r $v" }   ;# pitfall 2: RMSF before fitting
set ref [atomselect top "name CA" frame 0]; set all [atomselect top all]
for {set f 0} {$f < $n} {incr f} { $cmp frame $f; $all frame $f; $all move [measure fit $cmp $ref]; puts $o "RMSD $f [measure rmsd $cmp $ref]" }
close $o
quit
