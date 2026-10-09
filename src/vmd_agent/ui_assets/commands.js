"use strict";
/* The console's command language: a handful of commands spelled like VMD's own (mol, animate, display, axes, color, rotate, scale) for the viewer, plus
 * vmd-agent's (files, look, workflow, ask). `parse(line)` only reads a line and says what it means; the page does the work. No dependencies.
 */
(function (root) {
  function words(line) {                                   // words, with "double" or 'single' quotes and {braces} kept together
    const out = []; const re = /"([^"]*)"|'([^']*)'|\{([^}]*)\}|(\S+)/g; let m;
    while ((m = re.exec(line)) !== null) out.push(m[1] !== undefined ? m[1] : m[2] !== undefined ? m[2] : m[3] !== undefined ? m[3] : m[4]);
    return out;
  }
  const STYLES = ["Lines", "Bonds", "DynamicBonds", "HBonds", "Points", "VDW", "CPK", "Licorice", "Beads", "Tube", "Trace", "Ribbons", "NewRibbons", "Cartoon", "NewCartoon", "PaperChain", "Twister", "QuickSurf", "MSMS", "Surf", "Dotted", "Solvent"];
  const COLORS = ["Name", "Type", "Element", "ResName", "ResType", "ResID", "Chain", "SegName", "Structure", "Molecule", "Beta", "Occupancy", "Mass", "Charge", "Index", "Backbone", "Fragment", "Position"];
  const colorWord = (t, at) => (String(t[at]).toLowerCase() === "colorid" && Number.isInteger(Number(t[at + 1])) ? "ColorID " + Number(t[at + 1]) : pick(t[at], COLORS));
  const pick = (value, list) => list.find(x => x.toLowerCase() === String(value).toLowerCase());
  const num = v => (v !== undefined && v !== "" && Number.isFinite(Number(v)) ? Number(v) : null);
  const onoff = v => ({ on: true, off: false, yes: true, no: false, "1": true, "0": false, true: true, false: false })[String(v).toLowerCase()];

  const HELP = [
    "Molecules    mol new FILE | mol addfile FILE [ID] | mol delete [ID] | mol top ID | mol list",
    "Drawing      mol representation STYLE | mol color METHOD | mol selection \"SEL\" | mol addrep [ID] | mol modselect REP ID \"SEL\" | mol modstyle REP ID STYLE",
    "             mol modcolor REP ID METHOD | mol showrep ID REP on|off | mol delrep REP ID        (styles: " + STYLES.join(" ") + "; colours: " + COLORS.join(" ") + ")",
    "Animation    animate goto N|start|end | animate forward|reverse|pause | animate speed FPS | animate style once|loop|rock",
    "Display      display projection Perspective|Orthographic | display depthcue on|off | display resetview | axes location Off|LowerLeft",
    "             color Display Background black|white|gray | rotate x|y|z by DEGREES | scale by FACTOR",
    "Agent        files | look TOOL FILE | workflow NAME FILE... | ask QUESTION... | clear | help",
    "Terminal     tools | tool NAME [flags] | tool NAME --help | workflow     (the real command line, run in your files folder; a leading vmd-agent is accepted)",
"Selections   VMD's own language, read by VMD: protein, water, backbone, name CA, resname LIG, chain A, resid 1 to 20, within 5 of resname LIG, same residue as ...",
    "Window       Everything above acts on a real VMD window (it is opened when needed); the display shows VMD's own snapshots.",
  ];

  function parse(line) {
    const t = words(String(line || "").trim());
    if (!t.length) return null;
    const A = t[0].toLowerCase(), B = (t[1] || "").toLowerCase();
    const bad = msg => ({ error: msg });
    switch (A) {
      case "help": case "?": return { cmd: "help" };
      case "clear": return { cmd: "clear" };
      case "files": return { cmd: "files" };
      case "ask": return t.length > 1 ? { cmd: "ask", text: t.slice(1).join(" ") } : bad("ask what? (ask Which residues touch the ligand?)");
      case "look": return t.length >= 3 ? { cmd: "look", tool: t[1], file: t[2] } : bad("usage: look TOOL FILE   (tools: inspect_files, detect_system, structure_stats, probe_video)");
      case "tool": case "tools": case "vmd-agent": return { cmd: "terminal", line: String(line).trim() };
      case "workflow": return t.length < 2 ? { cmd: "terminal", line: "workflow" } : t.length >= 3 ? { cmd: "workflow", name: t[1], files: t.slice(2) } : bad("usage: workflow NAME FILE...   (for example: workflow equilibration_check run.psf run.dcd)");
      case "mol": switch (B) {
        case "new": return t[2] ? { cmd: "mol.new", file: t[2] } : bad("usage: mol new FILE");
        case "addfile": return t[2] ? { cmd: "mol.addfile", file: t[2], id: num(t[3]) } : bad("usage: mol addfile TRAJECTORY [ID]");
        case "delete": return { cmd: "mol.delete", id: t[2] === undefined || t[2] === "top" ? null : num(t[2]) };
        case "top": return num(t[2]) !== null ? { cmd: "mol.top", id: num(t[2]) } : bad("usage: mol top ID");
        case "list": return { cmd: "mol.list" };
        case "representation": { const s = pick(t[2], STYLES); return s ? { cmd: "mol.default", style: s } : bad("styles: " + STYLES.join(", ")); }
        case "color": { const c = colorWord(t, 2); return c ? { cmd: "mol.default", color: c } : bad("colours: " + COLORS.join(", ") + ", ColorID N"); }
        case "selection": return t[2] ? { cmd: "mol.default", sel: t.slice(2).join(" ") } : bad('usage: mol selection "protein"');
        case "addrep": return { cmd: "mol.addrep", id: num(t[2]) };
        case "modselect": return num(t[2]) !== null && num(t[3]) !== null && t[4] ? { cmd: "mol.modrep", rep: num(t[2]), id: num(t[3]), sel: t.slice(4).join(" ") } : bad('usage: mol modselect REP ID "SELECTION"');
        case "modstyle": { const s = pick(t[4], STYLES); return num(t[2]) !== null && num(t[3]) !== null && s ? { cmd: "mol.modrep", rep: num(t[2]), id: num(t[3]), style: s } : bad("usage: mol modstyle REP ID STYLE (" + STYLES.join(", ") + ")"); }
        case "modcolor": { const c = colorWord(t, 4); return num(t[2]) !== null && num(t[3]) !== null && c ? { cmd: "mol.modrep", rep: num(t[2]), id: num(t[3]), color: c } : bad("usage: mol modcolor REP ID METHOD (" + COLORS.join(", ") + ", ColorID N)"); }
        case "showrep": { const v = onoff(t[4]); return num(t[2]) !== null && num(t[3]) !== null && v !== undefined ? { cmd: "mol.modrep", id: num(t[2]), rep: num(t[3]), shown: v } : bad("usage: mol showrep ID REP on|off"); }
        case "delrep": return num(t[2]) !== null && num(t[3]) !== null ? { cmd: "mol.delrep", rep: num(t[2]), id: num(t[3]) } : bad("usage: mol delrep REP ID");
        default: return bad("mol what? (new, addfile, delete, top, list, representation, color, selection, addrep, modselect, modstyle, modcolor, showrep, delrep)");
      }
      case "animate": switch (B) {
        case "goto": { const v = t[2] === "start" ? 0 : t[2] === "end" ? Infinity : num(t[2]); return v !== null ? { cmd: "animate.goto", frame: v } : bad("usage: animate goto N|start|end"); }
        case "forward": case "reverse": case "pause": return { cmd: "animate." + B };
        case "speed": return num(t[2]) > 0 ? { cmd: "animate.speed", fps: num(t[2]) } : bad("usage: animate speed FRAMES_PER_SECOND");
        case "style": { const s = ["once", "loop", "rock"].find(x => x === String(t[2]).toLowerCase()); return s ? { cmd: "animate.style", style: s } : bad("usage: animate style once|loop|rock"); }
        default: return bad("animate what? (goto, forward, reverse, pause, speed, style)");
      }
      case "display": switch (B) {
        case "projection": { const p = pick(t[2], ["Perspective", "Orthographic"]); return p ? { cmd: "display.projection", projection: p } : bad("usage: display projection Perspective|Orthographic"); }
        case "depthcue": { const v = onoff(t[2]); return v !== undefined ? { cmd: "display.depthcue", on: v } : bad("usage: display depthcue on|off"); }
        case "resetview": return { cmd: "display.reset" };
        default: return bad("display what? (projection, depthcue, resetview)");
      }
      case "axes": { const p = pick(t[2], ["Off", "LowerLeft"]); return B === "location" && p ? { cmd: "axes", location: p } : bad("usage: axes location Off|LowerLeft"); }
      case "color": { const bg = pick(t[3], ["black", "white", "gray"]); return B === "display" && String(t[2]).toLowerCase() === "background" && bg ? { cmd: "background", color: bg } : bad("usage: color Display Background black|white|gray"); }
      case "rotate": { const ax = ["x", "y", "z"].find(a => a === B); return ax && String(t[2]).toLowerCase() === "by" && num(t[3]) !== null ? { cmd: "rotate", axis: ax, degrees: num(t[3]) } : bad("usage: rotate x|y|z by DEGREES"); }
      case "scale": return (B === "by" || B === "to") && num(t[2]) > 0 ? { cmd: "scale", mode: B, factor: num(t[2]) } : bad("usage: scale by FACTOR  or  scale to FACTOR");
      default: return bad(`unknown command "${t[0]}". Type help for the list.`);
    }
  }
  const api = { parse, words, HELP, STYLES, COLORS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VACommands = api;
})(typeof window !== "undefined" ? window : globalThis);
