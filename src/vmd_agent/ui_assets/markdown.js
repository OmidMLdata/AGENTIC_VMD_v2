"use strict";
/* A small, safe Markdown renderer for the chat: everything is HTML-escaped first, then headings, **bold**, *italic*, `code`, fenced code, lists and
 * tables are turned into tags. No raw HTML from a model ever reaches the page; links are not made (a model's link is not something to click). No dependencies. */
(function (root) {
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  function inline(s) {
    s = esc(s);
    s = s.replace(/`([^`\n]+)`/g, (_, c) => "<code>" + c + "</code>");
    s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    return s;
  }
  function render(text) {
    const lines = String(text || "").replace(/\r/g, "").split("\n"), out = []; let i = 0;
    const isRow = l => /^\s*\|.*\|\s*$/.test(l), isSep = l => /^\s*\|[\s:|-]+\|\s*$/.test(l);
    while (i < lines.length) {
      const l = lines[i];
      if (/^```/.test(l)) { const buf = []; i++; while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]); i++; out.push("<pre><code>" + esc(buf.join("\n")) + "</code></pre>"); continue; }
      if (isRow(l) && i + 1 < lines.length && isSep(lines[i + 1])) {
        const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        let h = "<table><thead><tr>" + cells(l).map(c => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>"; i += 2;
        while (i < lines.length && isRow(lines[i])) { h += "<tr>" + cells(lines[i]).map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>"; i++; }
        out.push(h + "</tbody></table>"); continue;
      }
      let m;
      if ((m = /^(#{1,4})\s+(.*)$/.exec(l))) { const k = Math.min(m[1].length + 2, 6); out.push(`<h${k}>` + inline(m[2]) + `</h${k}>`); i++; continue; }
      if (/^\s*[-*]\s+/.test(l)) { const items = []; while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push("<li>" + inline(lines[i++].replace(/^\s*[-*]\s+/, "")) + "</li>"); out.push("<ul>" + items.join("") + "</ul>"); continue; }
      if (/^\s*\d+[.)]\s+/.test(l)) { const items = []; while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push("<li>" + inline(lines[i++].replace(/^\s*\d+[.)]\s+/, "")) + "</li>"); out.push("<ol>" + items.join("") + "</ol>"); continue; }
      if (!l.trim()) { i++; continue; }
      const para = [inline(l)]; i++;                       // always takes this line: a table row whose separator has not streamed in yet is plain text for now
      while (i < lines.length && lines[i].trim() && !/^```|^#{1,4}\s|^\s*[-*]\s|^\s*\d+[.)]\s/.test(lines[i]) && !(isRow(lines[i]) && i + 1 < lines.length && isSep(lines[i + 1]))) para.push(inline(lines[i++]));
      out.push("<p>" + para.join("<br>") + "</p>");
    }
    return out.join("");
  }
  const api = { render, esc };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VAMarkdown = api;
})(typeof window !== "undefined" ? window : globalThis);
