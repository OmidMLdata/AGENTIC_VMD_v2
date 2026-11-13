# Manual VMD: what an experienced user types in VMD's Tk console (standard tutorial idioms)
mol new protein.pdb type pdb waitfor all
animate delete all                         ;# drop the PDB's own coordinates so frame N = trajectory frame N
mol addfile protein.dcd type dcd waitfor all
set n [molinfo top get numframes]
set out [open manual_out.txt w]
puts $out "NFRAMES $n"
# --- radius of gyration (protein, per frame)
set p [atomselect top protein]
for {set f 0} {$f < $n} {incr f} { $p frame $f; puts $out "RGYR $f [measure rgyr $p]" }
# --- SASA (probe 1.4 A)
for {set f 0} {$f < $n} {incr f} { $p frame $f; puts $out "SASA $f [measure sasa 1.4 $p]" }
# --- hydrogen bonds (3.0 A, 20 deg), count per frame
for {set f 0} {$f < $n} {incr f} { $p frame $f; puts $out "HB $f [llength [lindex [measure hbonds 3.0 20 $p] 0]]" }
# --- phi/psi of frame 0
set ca [atomselect top "protein and name CA" frame 0]
foreach r [$ca get resid] phi [$ca get phi] psi [$ca get psi] { puts $out "TOR $r $phi $psi" }
# --- CA RMSD to frame 0 after least-squares fit
set ref [atomselect top "name CA" frame 0]
set cmp [atomselect top "name CA"]
set all [atomselect top all]
for {set f 0} {$f < $n} {incr f} {
  $cmp frame $f; $all frame $f
  $all move [measure fit $cmp $ref]
  puts $out "RMSD $f [measure rmsd $cmp $ref]"
}
# --- CA RMSF over the (now fitted) trajectory
foreach r [$cmp get resid] v [measure rmsf $cmp first 0 last -1 step 1] { puts $out "RMSF $r $v" }
close $out
quit
