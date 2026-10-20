// Cleaner interface. TOKEN comes from index.html (injected by the server).
const $ = id => document.getElementById(id);
const api = (path, body) => fetch(path, {
  method: body ? "POST" : "GET",
  headers: { "X-Token": TOKEN, "Content-Type": "application/json" },
  body: body && JSON.stringify(body)
}).then(r => r.json()).catch(() => ({ error: "no response from the server. Is it still running?" }));
const fmt = b => { const u=["B","KB","MB","GB","TB"]; let i=0; while(b>=1024&&i<4){b/=1024;i++} return b.toFixed(i?1:0)+" "+u[i] };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const icons = () => lucide.createIcons();
const plural = (n, word, many) => `${n.toLocaleString()} ${n === 1 ? word : many || word + "s"}`;
const dark = matchMedia("(prefers-color-scheme: dark)");

// Risk levels: color + icon + text (never color alone)
const RISK = {
  safe:    { label: "Safe to delete", short: "Safe",     icon: "shield-check", chip: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300", dot: "bg-emerald-500", ring: "border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-500/10" },
  neutral: { label: "Review it yourself", short: "Review",  icon: "help-circle",  chip: "bg-slate-200 text-slate-700 dark:bg-slate-700/60 dark:text-slate-300",               dot: "bg-slate-400",   ring: "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50" },
  caution: { label: "Caution",       short: "Caution",  icon: "alert-triangle", chip: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",           dot: "bg-amber-500",   ring: "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-500/10" },
  danger:  { label: "Dangerous: don't delete", short: "Dangerous", icon: "shield-alert", chip: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",          dot: "bg-rose-500",    ring: "border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-500/10" },
};
const chip = (risk, text) => `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${RISK[risk].chip}"><i data-lucide="${RISK[risk].icon}" class="w-3.5 h-3.5"></i>${text ?? RISK[risk].short}</span>`;

let report = null, folder = null, files = [], idx = 0, freed = 0, trashed = 0, history = [];
let SEP = "/", lastUndo = null;  // SEP: the system folder separator ("\\" on Windows)
const relOf = (dir, name) => dir === "." ? name : dir + SEP + name;
let riskFilter = "all", charts = [], info = null, infoOpen = true;

/* ---------------- Report ---------------- */
function kpi(icon, label, value, sub = "", accent = "text-indigo-600 dark:text-indigo-400") {
  return `<div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5">
    <div class="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400"><i data-lucide="${icon}" class="w-4 h-4 ${accent}"></i>${label}</div>
    <div class="text-3xl font-bold mt-2">${value}</div><div class="text-xs text-slate-500 dark:text-slate-400 mt-1">${sub}</div></div>`;
}
const chartCard = (id, title, icon, n) => `
  <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5">
    <h2 class="font-semibold flex items-center gap-2 mb-3"><i data-lucide="${icon}" class="w-4 h-4 text-slate-400"></i>${title}</h2>
    <div style="height:${Math.max(120, n * 26 + 30)}px"><canvas id="${id}"></canvas></div></div>`;

function renderReport() {
  charts.forEach(c => c.destroy()); charts = [];
  if (!report) return;
  const counts = { safe: 0, caution: 0, danger: 0, neutral: 0 };
  report.folders.forEach(f => counts[f.risk] += f.size);
  const sets = {
    cTop: report.top_level.slice(0, 12), cHeavy: report.heaviest.slice(0, 15),
    cExt: report.by_ext.slice(0, 12), cFiles: report.largest_files.slice(0, 15),
  };
  $("report").innerHTML = `
    <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5 fade-in">
      ${kpi("hard-drive", "Total scanned", fmt(report.total), esc(report.root))}
      ${kpi("files", "Files", report.file_count.toLocaleString(), `${plural(report.folders.length, "folder")} with files`)}
      ${kpi("shield-check", "Safe to clean", fmt(report.safe_total), "caches, temporary files, builds", "text-emerald-600 dark:text-emerald-400")}
      ${kpi("leaf", "Freed this session", fmt(freed), `${plural(trashed, "file")} in the Trash`)}
    </div>

    <div class="grid lg:grid-cols-[1fr_1.4fr] gap-5 mb-5 fade-in">
      <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5">
        <h2 class="font-semibold mb-1 flex items-center gap-2"><i data-lucide="gauge" class="w-4 h-4 text-slate-400"></i>Space by risk level</h2>
        <p class="text-xs text-slate-500 dark:text-slate-400 mb-4">Automatic estimate based on the type and location of each folder.</p>
        <div class="flex h-4 rounded-full overflow-hidden gap-0.5 mb-4">
          ${["safe","neutral","caution","danger"].map(r => counts[r] ? `<div class="${RISK[r].dot}" style="flex:${counts[r]}" title="${RISK[r].short}: ${fmt(counts[r])}"></div>` : "").join("")}
        </div>
        <div class="space-y-2">${["safe","neutral","caution","danger"].map(r => `
          <div class="flex items-center justify-between text-sm">${chip(r, RISK[r].label)}<span class="font-medium">${fmt(counts[r])}</span></div>`).join("")}</div>
      </div>
      <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5">
        <h2 class="font-semibold mb-1 flex items-center gap-2"><i data-lucide="sparkles" class="w-4 h-4 text-emerald-500"></i>Where you can clean without worry</h2>
        <p class="text-xs text-slate-500 dark:text-slate-400 mb-3">Caches and temporary files are recreated by programs when they need them.</p>
        <div class="space-y-1 max-h-64 overflow-auto scroll-thin">
          ${report.safe_spots.map(([p, s]) => `
            <button class="spot w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-left" data-p="${esc(p)}">
              <i data-lucide="folder" class="w-4 h-4 text-emerald-500 shrink-0"></i>
              <span class="truncate flex-1 text-sm">${esc(p)}</span>
              <span class="text-sm text-slate-500 dark:text-slate-400">${fmt(s)}</span>
              <i data-lucide="chevron-right" class="w-4 h-4 text-slate-400"></i>
            </button>`).join("") || '<p class="text-sm text-slate-500">No cache found in this folder.</p>'}
        </div>
      </div>
    </div>

    <div class="grid lg:grid-cols-2 gap-5 fade-in">
      ${chartCard("cTop", "Top folders", "folder-tree", sets.cTop.length)}
      ${chartCard("cHeavy", "Heaviest folders (any level)", "folders", sets.cHeavy.length)}
      ${chartCard("cExt", "By file type", "file-type", sets.cExt.length)}
      ${chartCard("cFiles", "Largest files", "file-box", sets.cFiles.length)}
    </div>`;
  icons();
  document.querySelectorAll(".spot").forEach(b => b.onclick = () => {
    const f = report.folders.find(f => f.path === b.dataset.p || f.path.startsWith(b.dataset.p + SEP));
    show("clean"); $("folderSearch").value = b.dataset.p; renderFolders();
    if (f) openFolder(f.path);
  });
  Object.entries(sets).forEach(([id, rows]) => drawBars(id, rows, id === "cExt"));
}

function drawBars(id, rows, isExt) {
  const isDark = dark.matches;
  const ink = isDark ? "#94a3b8" : "#64748b", grid = isDark ? "#1e293b" : "#eef2f7";
  const short = s => s.length > 34 ? "…" + s.slice(-33) : s;
  charts.push(new Chart($(id), {
    type: "bar",
    data: { labels: rows.map(r => r[0]), datasets: [{ data: rows.map(r => r[1]),
      backgroundColor: isDark ? "#818cf8" : "#4f46e5", hoverBackgroundColor: isDark ? "#a5b4fc" : "#4338ca",
      borderRadius: 4, borderSkipped: "start", barThickness: 14 }] },
    options: {
      indexAxis: "y", maintainAspectRatio: false, animation: { duration: 400 },
      plugins: { legend: { display: false }, tooltip: {
        backgroundColor: isDark ? "#0f172a" : "#1e293b", padding: 10, displayColors: false,
        callbacks: { label: c => fmt(c.raw) + (isExt ? ` · ${plural(rows[c.dataIndex][2], "file")}` : "") } } },
      scales: {
        x: { grid: { color: grid }, border: { display: false }, ticks: { color: ink, callback: v => fmt(v), maxTicksLimit: 5 } },
        y: { grid: { display: false }, border: { display: false }, ticks: { color: ink, callback: function (v) { return short(this.getLabelForValue(v)) } } },
      },
    },
  }));
}

/* ---------------- Clean ---------------- */
function renderRiskFilter() {
  const opts = [["all", "All"], ["safe", "Safe"], ["neutral", "Review"], ["caution", "Caution"], ["danger", "Dangerous"]];
  $("riskFilter").innerHTML = opts.map(([k, l]) => `
    <button data-r="${k}" class="px-2.5 py-1 rounded-full text-xs font-medium border ${riskFilter === k
      ? "bg-indigo-600 border-indigo-600 text-white"
      : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"}">
      ${k !== "all" ? `<span class="inline-block w-2 h-2 rounded-full mr-1 ${RISK[k].dot}"></span>` : ""}${l}</button>`).join("");
  document.querySelectorAll("#riskFilter button").forEach(b => b.onclick = () => { riskFilter = b.dataset.r; renderRiskFilter(); renderFolders() });
}

function visibleFolders() {
  const q = $("folderSearch").value.toLowerCase();
  return report.folders.filter(f => (riskFilter === "all" || f.risk === riskFilter) && (!q || f.path.toLowerCase().includes(q)) && f.count > 0);
}

function renderFolders() {
  if (!report) return;
  const list = visibleFolders().slice(0, 400);
  $("folders").innerHTML = list.map(f => `
    <button class="fold w-full text-left px-3 py-2.5 rounded-xl mb-1 transition ${f.path === folder
      ? "bg-indigo-50 dark:bg-indigo-500/15 ring-1 ring-indigo-300 dark:ring-indigo-700" : "hover:bg-slate-100 dark:hover:bg-slate-800"}" data-p="${esc(f.path)}">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full shrink-0 ${RISK[f.risk].dot}" title="${RISK[f.risk].short}"></span>
        <span class="truncate text-sm font-medium" style="direction:rtl;text-align:left" title="${esc(f.path)}">&lrm;${esc(f.path)}&lrm;</span>
      </div>
      <div class="flex items-center justify-between mt-1 pl-4 text-xs text-slate-500 dark:text-slate-400">
        <span>${fmt(f.size)} · ${plural(f.count, "file")}</span><span>${RISK[f.risk].short}</span>
      </div>
      ${f.label ? `<div class="pl-4 mt-1"><span class="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300 max-w-full truncate"><i data-lucide="tag" class="w-3 h-3 shrink-0"></i>${esc(f.label)}</span></div>` : ""}
    </button>`).join("") || `<p class="text-sm text-slate-500 p-4 text-center">No folders match this filter.</p>`;
  document.querySelectorAll(".fold").forEach(el => el.onclick = () => openFolder(el.dataset.p));
  icons();
}

function emptyViewer() {
  $("viewer").innerHTML = `<div class="flex-1 grid place-items-center text-center text-slate-500 dark:text-slate-400">
    <div><i data-lucide="mouse-pointer-click" class="w-12 h-12 mx-auto mb-3 opacity-40"></i>
    <p class="font-medium">Pick a folder on the left</p>
    <p class="text-sm mt-1">Files show up one at a time, largest first.</p></div></div>`;
  icons();
}

async function openFolder(path) {
  folder = path; idx = 0; history = []; info = null;
  const q = encodeURIComponent(path);
  [files, info] = await Promise.all([api("/api/files?folder=" + q), api("/api/folder_info?folder=" + q)]);
  if (info.error) info = null;
  renderFolders(); renderViewer();
}

function previewHTML(f, dir = folder) {
  const src = "/api/preview?t=" + TOKEN + "&path=" + encodeURIComponent(relOf(dir, f.name));
  const box = "max-h-[46vh] max-w-full rounded-lg";
  if (f.mime.startsWith("image/")) return `<img src="${src}" class="${box} object-contain shadow">`;
  if (f.mime.startsWith("video/")) return `<video src="${src}" controls class="${box}"></video>`;
  if (f.mime.startsWith("audio/")) return `<div class="text-center"><i data-lucide="music" class="w-14 h-14 mx-auto mb-4 opacity-40"></i><audio src="${src}" controls></audio></div>`;
  if (f.mime === "application/pdf") return `<iframe src="${src}" class="w-full h-[46vh] rounded-lg bg-white"></iframe>`;
  if (f.mime.startsWith("text/") || /json|xml|javascript|x-sh|x-python|yaml/.test(f.mime) || f.size < 20000 && !f.mime) {
    fetch(src).then(r => r.text()).then(t => { const p = $("txt"); if (p) p.textContent = t });
    return `<pre id="txt" class="w-full h-[46vh] overflow-auto scroll-thin text-xs p-4 font-mono whitespace-pre-wrap">loading…</pre>`;
  }
  const ext = (f.name.split(".").pop() || "").toUpperCase().slice(0, 5);
  return `<div class="text-center text-slate-400"><div class="relative inline-block"><i data-lucide="file" class="w-24 h-24 stroke-1"></i>
    <span class="absolute inset-x-0 bottom-6 text-xs font-bold">${esc(ext)}</span></div><p class="text-sm mt-2">No preview for this type</p></div>`;
}

function renderViewer(anim) {
  const v = $("viewer");
  if (!folder) return emptyViewer();
  const fo = report.folders.find(f => f.path === folder);
  if (idx >= files.length) {
    const list = visibleFolders(), i = list.findIndex(f => f.path === folder);
    v.innerHTML = `<div class="flex-1 grid place-items-center text-center fade-in"><div>
      <div class="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-500/15 grid place-items-center mx-auto mb-4"><i data-lucide="check" class="w-8 h-8 text-emerald-600 dark:text-emerald-400"></i></div>
      <p class="text-lg font-semibold">Folder reviewed!</p><p class="text-sm text-slate-500 mt-1 break-all">${esc(folder)}</p>
      <div class="flex gap-2 justify-center mt-5">
        ${history.length ? `<button id="backBtn" class="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm">Back</button>` : ""}
        ${list[i + 1] ? `<button id="nextFolder" class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium inline-flex items-center gap-1.5">Next folder<i data-lucide="arrow-right" class="w-4 h-4"></i></button>` : ""}
      </div></div></div>`;
    icons();
    $("nextFolder") && ($("nextFolder").onclick = () => openFolder(list[i + 1].path));
    $("backBtn") && ($("backBtn").onclick = back);
    return;
  }
  const f = files[idx], R = RISK[f.risk], pct = Math.round(idx / files.length * 100);
  v.innerHTML = `
    <div class="flex items-center justify-between gap-3 mb-3">
      <div class="min-w-0">
        <div class="text-xs text-slate-500 dark:text-slate-400 truncate flex items-center gap-1"><i data-lucide="folder-open" class="w-3.5 h-3.5 shrink-0"></i>${esc(folder)}</div>
        <div class="text-xs text-slate-400 mt-0.5">folder: ${chip(fo?.risk || "neutral")}</div>
      </div>
      <div class="flex items-center gap-3 shrink-0">
        <button id="bulkBtn" class="px-3 py-1.5 rounded-lg border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-500/10 text-sm font-medium inline-flex items-center gap-1.5"><i data-lucide="trash" class="w-4 h-4"></i>Delete all</button>
        <span class="text-sm text-slate-500 dark:text-slate-400">${idx + 1} / ${files.length}</span>
      </div>
    </div>
    <div class="h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full mb-4 overflow-hidden"><div class="h-full bg-indigo-500 transition-all" style="width:${pct}%"></div></div>
    ${infoPanel()}

    <div id="card" class="flex-1 flex flex-col ${anim || "fade-in"}">
      <div class="flex-1 min-h-[300px] grid place-items-center rounded-xl bg-slate-100 dark:bg-slate-800/60 overflow-hidden p-2">${previewHTML(f)}</div>
      <div class="mt-4 flex items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="text-lg font-semibold break-all">${esc(f.name)}</div>
          <div class="text-sm text-slate-500 dark:text-slate-400 mt-0.5 flex flex-wrap gap-x-3">
            <span class="inline-flex items-center gap-1"><i data-lucide="weight" class="w-3.5 h-3.5"></i>${fmt(f.size)}</span>
            <span class="inline-flex items-center gap-1"><i data-lucide="calendar" class="w-3.5 h-3.5"></i>${new Date(f.mtime * 1000).toLocaleDateString()}</span>
            <span class="inline-flex items-center gap-1"><i data-lucide="file-type" class="w-3.5 h-3.5"></i>${esc(f.mime || "unknown type")}</span>
          </div>
        </div>
      </div>
      <div class="mt-3 rounded-xl border p-3 ${R.ring}">
        <div class="flex items-center gap-2 font-semibold text-sm">${chip(f.risk, R.label)}</div>
        <ul class="mt-2 text-sm text-slate-600 dark:text-slate-300 space-y-0.5 list-disc pl-5">${f.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
      </div>
    </div>

    <div class="grid grid-cols-[auto_1fr_1fr] gap-3 mt-4">
      <button id="backBtn" ${history.length ? "" : "disabled"} class="px-4 rounded-xl border border-slate-200 dark:border-slate-700 disabled:opacity-30" title="Back (Backspace)"><i data-lucide="undo-2" class="w-5 h-5"></i></button>
      <button id="delBtn" class="py-3.5 rounded-xl bg-rose-600 hover:bg-rose-500 active:scale-[.98] text-white font-semibold flex items-center justify-center gap-2 transition">
        <i data-lucide="trash-2" class="w-5 h-5"></i>Delete <kbd class="text-xs px-1.5 rounded border border-white/40">←</kbd></button>
      <button id="keepBtn" class="py-3.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 active:scale-[.98] text-white font-semibold flex items-center justify-center gap-2 transition">
        <i data-lucide="check" class="w-5 h-5"></i>Keep <kbd class="text-xs px-1.5 rounded border border-white/40">→</kbd></button>
    </div>
    <p class="text-xs text-slate-500 dark:text-slate-400 mt-3 flex items-center gap-1.5"><i data-lucide="info" class="w-3.5 h-3.5"></i>"Delete" moves files to the Trash, so you can get them back. The risk rating is an estimate, not a guarantee.</p>`;
  icons();
  $("delBtn").onclick = del; $("keepBtn").onclick = keep; $("backBtn").onclick = back; $("bulkBtn").onclick = () => bulkModal();
  $("info") && ($("info").ontoggle = e => infoOpen = e.target.open);
}

// "About this folder": explains what the folder is (text comes from the server; **x** becomes bold)
function infoPanel(inf = info, id = "info") {
  if (!inf) return "";
  const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  const pills = (title, arr, icon) => arr.length ? `<div class="mt-2 text-xs text-slate-500 dark:text-slate-400">${title}:
    <span class="inline-flex flex-wrap gap-1 align-middle">${arr.map(n => `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono"><i data-lucide="${icon}" class="w-3 h-3"></i>${esc(n)}</span>`).join("")}</span></div>` : "";
  return `<details id="${id}" ${infoOpen ? "open" : ""} class="mb-4 rounded-xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/60 dark:bg-indigo-500/5 group">
    <summary class="cursor-pointer list-none px-4 py-2.5 flex items-center gap-2 text-sm font-semibold">
      <i data-lucide="info" class="w-4 h-4 text-indigo-500"></i>About this folder
      ${inf.label ? `<span class="font-normal text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-500/20 dark:text-indigo-200 truncate">${esc(inf.label)}</span>` : ""}
      <i data-lucide="chevron-down" class="w-4 h-4 ml-auto text-slate-400 transition group-open:rotate-180"></i>
    </summary>
    <div class="px-4 pb-3 text-sm text-slate-700 dark:text-slate-300">
      <ul class="space-y-1">${inf.lines.map(l => `<li class="flex gap-2"><span class="text-indigo-400 mt-0.5">•</span><span>${md(l)}</span></li>`).join("")}</ul>
      ${id === "info" ? pills("Subfolders", inf.subdirs, "folder") : ""}
      ${pills("Sample files", inf.samples, "file")}
    </div>
  </details>`;
}

function animateOut(cls) { const c = $("card"); c && c.classList.add(cls); return new Promise(r => setTimeout(r, 180)) }

let busy = false;
async function keep() {
  if (busy || idx >= files.length) return; busy = true;
  await animateOut("card-out-right");
  history.push({ type: "keep" }); idx++; renderViewer(); busy = false;
}
async function back() {
  if (busy) return;
  const h = history.pop(); if (!h) return;
  if (h.type === "keep") { idx--; return renderViewer() }
  // deleted file: take it out of the Trash and show it again
  busy = true;
  try { await undo(h.op) } finally { busy = false }
}
async function del(confirmed) {
  const f = files[idx]; if (!f || busy) return;
  if (f.risk === "danger" && confirmed !== true) return confirmDanger(f);
  busy = true;
  const r = await api("/api/trash", { folder, name: f.name });
  if (r.error) { busy = false; return toast("Error: " + r.error, "error") }
  await animateOut("card-out-left");
  freed = r.freed; trashed++; history.push({ type: "del", op: r.undo?.id }); setUndo(r.undo);
  files.splice(idx, 1);
  const fo = report.folders.find(x => x.path === folder);
  if (fo) { fo.size -= f.size; fo.count--; }
  updateStat(); renderViewer(); renderFolders(); busy = false;
  toast(`${f.name} went to the Trash`, "ok", undoAction(r.undo));
}

function confirmDanger(f, onOk = () => del(true)) {
  const m = $("modal");
  m.innerHTML = `<div class="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-md w-full shadow-xl fade-in">
    <div class="w-12 h-12 rounded-full bg-rose-100 dark:bg-rose-500/15 grid place-items-center mb-4"><i data-lucide="shield-alert" class="w-6 h-6 text-rose-600"></i></div>
    <h3 class="text-lg font-semibold">Are you sure?</h3>
    <p class="text-sm text-slate-600 dark:text-slate-300 mt-2"><b class="break-all">${esc(f.name)}</b> looks important:</p>
    <ul class="text-sm text-slate-600 dark:text-slate-300 list-disc pl-5 mt-1">${f.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
    <div class="flex gap-2 justify-end mt-6">
      <button id="mCancel" class="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium">Cancel</button>
      <button id="mOk" class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-sm font-medium">Delete anyway</button>
    </div></div>`;
  m.classList.replace("hidden", "flex"); icons();
  const close = () => m.classList.replace("flex", "hidden");
  $("mCancel").onclick = close; $("mOk").onclick = () => { close(); onOk() };
  m.onclick = e => { if (e.target === m) close() };  // no "return false", which would cancel clicks on radios/checkboxes
}

// "Delete all": this folder's files or the whole folder (with subfolders)
async function bulkModal(target = folder, onDone = afterBulk, defaultMode) {
  const m = $("modal");
  m.innerHTML = `<div class="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-lg w-full shadow-xl fade-in text-center"><i data-lucide="loader-2" class="w-8 h-8 mx-auto animate-spin text-indigo-500"></i></div>`;
  m.classList.replace("hidden", "flex"); icons();
  const close = () => m.classList.replace("flex", "hidden");
  m.onclick = e => { if (e.target === m) close() };
  const pv = await api("/api/bulk_preview?folder=" + encodeURIComponent(target));
  if (pv.error) { close(); return toast(pv.error, "error") }
  // a folder with no loose files (only subfolders) opens on "whole folder"
  let mode = pv.is_root ? "files" : defaultMode || (pv.files.count ? "files" : "tree");

  const breakdown = st => ["safe", "neutral", "caution", "danger"].filter(r => st.by_risk[r]).map(r => `
    <div class="flex items-center justify-between text-sm py-0.5">${chip(r, RISK[r].label)}
      <span class="text-slate-600 dark:text-slate-300">${plural(st.by_risk[r][0], "file")} · ${fmt(st.by_risk[r][1])}</span></div>`).join("");
  const option = (k, title, sub, disabled) => `
    <label class="flex gap-3 p-3 rounded-xl border cursor-pointer ${disabled ? "opacity-40 pointer-events-none" : ""}
      ${mode === k ? "border-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 dark:border-indigo-600" : "border-slate-200 dark:border-slate-700"}">
      <input type="radio" name="bm" value="${k}" ${mode === k ? "checked" : ""} ${disabled ? "disabled" : ""} class="mt-1 accent-indigo-600">
      <div><div class="font-medium text-sm">${title}</div><div class="text-xs text-slate-500 dark:text-slate-400">${sub}</div></div></label>`;

  function render() {
    const st = mode === "files" ? pv.files : pv.tree;
    const danger = st.by_risk.danger;
    const size = mode === "files" && danger ? st.size - danger[1] : st.size;
    const count = mode === "files" && danger ? st.count - danger[0] : st.count;
    m.innerHTML = `<div class="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-lg w-full shadow-xl">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-10 h-10 rounded-full bg-rose-100 dark:bg-rose-500/15 grid place-items-center shrink-0"><i data-lucide="trash" class="w-5 h-5 text-rose-600"></i></div>
        <div class="min-w-0"><h3 class="text-lg font-semibold">Delete all</h3><p class="text-xs text-slate-500 truncate">${esc(target)}</p></div>
      </div>
      <div class="space-y-2">
        ${option("files", `Only the files in this folder`, `${plural(pv.files.count, "file")} · ${fmt(pv.files.size)}; subfolders stay untouched`)}
        ${option("tree", `The whole folder, with subfolders`, pv.is_root ? "not available for the scanned folder" : `${plural(pv.tree.count, "file")} in ${plural(pv.tree.subfolders + 1, "folder")} · ${fmt(pv.tree.size)}`, pv.is_root)}
      </div>
      <div class="mt-4 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60">${breakdown(st) || '<p class="text-sm text-slate-500">Nothing to delete.</p>'}</div>
      ${danger ? `<label class="mt-3 flex gap-2 items-start text-sm text-rose-700 dark:text-rose-300">
        <input type="checkbox" id="bmDanger" class="mt-1 accent-rose-600">
        <span>${mode === "files"
          ? `Also include the ${plural(danger[0], "dangerous file")}; otherwise they are skipped.`
          : `I understand this folder has content marked as dangerous and I want to delete it anyway.`}</span></label>` : ""}
      <p class="text-xs text-slate-500 dark:text-slate-400 mt-3 flex items-center gap-1.5"><i data-lucide="info" class="w-3.5 h-3.5"></i>Everything goes to the Trash, so you can restore it.</p>
      <div class="flex gap-2 justify-end mt-5">
        <button id="bmCancel" class="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium">Cancel</button>
        <button id="bmOk" class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-sm font-medium"
          ${!st.count || (mode === "tree" && danger) ? "disabled" : ""}>Delete ${plural(mode === "files" ? count : st.count, "file")} · ${fmt(size)}</button>
      </div></div>`;
    icons();
    m.querySelectorAll("input[name=bm]").forEach(r => r.onchange = () => { mode = r.value; render() });
    const cb = $("bmDanger"), ok = $("bmOk");
    if (cb) cb.onchange = () => {
      if (mode === "tree") ok.disabled = !cb.checked;
      else ok.textContent = `Delete ${plural(cb.checked ? st.count : count, "file")} · ${fmt(cb.checked ? st.size : size)}`;
    };
    $("bmCancel").onclick = close;
    ok.onclick = async () => {
      ok.disabled = true; ok.textContent = "Deleting…";
      const r = await api("/api/trash_bulk", { folder: target, mode, include_danger: !!(cb && cb.checked) });
      close();
      if (r.error) return toast("Error: " + r.error, "error");
      freed = r.freed; trashed += r.trashed; setUndo(r.undo);
      if (mode === "tree") report.folders = report.folders.filter(f => f.path !== target && !f.path.startsWith(target + SEP));
      onDone(mode, r, target);
    };
  }
  render();
}

async function afterBulk(mode, r) {
  if (mode === "tree") {
    folder = null; files = [];
    emptyViewer();
  } else {
    files = await api("/api/files?folder=" + encodeURIComponent(folder)); idx = 0; history = [];
    const fo = report.folders.find(x => x.path === folder);
    if (fo) { fo.count = files.length; fo.size = files.reduce((a, f) => a + f.size, 0) }
    renderViewer();
  }
  updateStat(); renderFolders();
  toast(`${plural(r.trashed, "file")} went to the Trash (${fmt(r.freed_now)})` + (r.skipped ? ` · ${plural(r.skipped, "dangerous file")} kept` : ""), "ok", undoAction(r.undo));
}

/* ---------------- Explore ---------------- */
let exPath = ".", exData = null, exInfo = null;
const fileIcon = m => m.startsWith("image/") ? "image" : m.startsWith("video/") ? "film" : m.startsWith("audio/") ? "music"
  : m === "application/pdf" ? "file-text" : /zip|tar|compress|rar|7z/.test(m) ? "file-archive" : m.startsWith("text/") ? "file-code" : "file";

async function explore(path) {
  exPath = path;
  const q = encodeURIComponent(path);
  const [d, inf] = await Promise.all([api("/api/browse?folder=" + q), api("/api/folder_info?folder=" + q)]);
  if (d.error) { toast(d.error, "error"); if (path !== ".") return explore("."); return }
  exData = d; exInfo = inf.error ? null : inf;
  renderExplore();
}

function renderExplore() {
  const d = exData, segs = d.path === "." ? [] : d.path.split(SEP);
  const max = Math.max(1, ...d.subdirs.map(x => x.size), ...d.files.map(x => x.size));
  const bar = size => `<div class="h-1.5 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden"><div class="h-full bg-indigo-500 rounded-full" style="width:${Math.max(.5, size / max * 100)}%"></div></div>`;
  const trashBtn = (cls, data) => `<button class="${cls} p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10" ${data} title="Move to the Trash"><i data-lucide="trash-2" class="w-4 h-4"></i></button>`;
  const row = (inner) => `<div class="grid grid-cols-[1fr_120px_90px_auto] sm:grid-cols-[1fr_160px_100px_auto] items-center gap-3 px-3 py-2 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/60">${inner}</div>`;

  $("explore").innerHTML = `
    <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 fade-in">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <nav class="flex flex-wrap items-center gap-1 text-sm min-w-0 flex-1">
          <button class="crumb px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5 font-medium" data-p="."><i data-lucide="hard-drive" class="w-4 h-4"></i>${esc(report.root.split(/[\\/]/).filter(Boolean).pop() || report.root)}</button>
          ${segs.map((sg, i) => `<i data-lucide="chevron-right" class="w-4 h-4 text-slate-400"></i>
            <button class="crumb px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 ${i === segs.length - 1 ? "font-semibold" : ""}" data-p="${esc(segs.slice(0, i + 1).join(SEP))}">${esc(sg)}</button>`).join("")}
        </nav>
        <span class="text-sm text-slate-500 dark:text-slate-400">${fmt(d.total)} · ${plural(d.count, "file")}</span>
        ${d.files.length ? `<button id="exReview" class="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-sm font-medium inline-flex items-center gap-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"><i data-lucide="layers" class="w-4 h-4"></i>Review one by one</button>` : ""}
        ${d.path !== "." ? `<button id="exBulk" class="px-3 py-1.5 rounded-lg border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-500/10 text-sm font-medium inline-flex items-center gap-1.5"><i data-lucide="trash" class="w-4 h-4"></i>Delete all</button>` : ""}
      </div>
      ${infoPanel(exInfo, "exInfo")}
      <div class="text-xs uppercase tracking-wide text-slate-400 px-3 mb-1 grid grid-cols-[1fr_120px_90px_auto] sm:grid-cols-[1fr_160px_100px_auto] gap-3"><span>Name</span><span>Size</span><span>Risk</span><span class="w-8"></span></div>
      ${d.subdirs.map((x, i) => row(`
        <button class="exDir flex items-center gap-2.5 min-w-0 text-left" data-i="${i}">
          <i data-lucide="folder" class="w-5 h-5 shrink-0 text-indigo-500 fill-indigo-100 dark:fill-indigo-500/20"></i>
          <span class="min-w-0"><span class="block truncate font-medium text-sm">${esc(x.name)}</span>
          ${x.label ? `<span class="block truncate text-xs text-indigo-600 dark:text-indigo-300">${esc(x.label)}</span>` : `<span class="block text-xs text-slate-400">${plural(x.count, "file")}</span>`}</span>
        </button>
        <div><div class="text-sm mb-1">${fmt(x.size)}</div>${bar(x.size)}</div>
        <div>${chip(x.risk)}</div>
        ${trashBtn("exDelDir", `data-i="${i}"`)}`)).join("")}
      ${d.files.map((f, i) => row(`
        <button class="exFile flex items-center gap-2.5 min-w-0 text-left" data-i="${i}">
          <i data-lucide="${fileIcon(f.mime)}" class="w-5 h-5 shrink-0 text-slate-400"></i>
          <span class="min-w-0"><span class="block truncate text-sm">${esc(f.name)}</span>
          <span class="block text-xs text-slate-400">${new Date(f.mtime * 1000).toLocaleDateString()}</span></span>
        </button>
        <div><div class="text-sm mb-1">${fmt(f.size)}</div>${bar(f.size)}</div>
        <div title="${esc(f.reasons.join(" · "))}">${chip(f.risk)}</div>
        ${trashBtn("exDelFile", `data-i="${i}"`)}`)).join("")}
      ${!d.subdirs.length && !d.files.length ? `<p class="text-center text-slate-500 py-10">Empty folder.</p>` : ""}
    </div>`;
  icons();
  document.querySelectorAll(".crumb").forEach(b => b.onclick = () => explore(b.dataset.p));
  document.querySelectorAll(".exDir").forEach(b => b.onclick = () => explore(d.subdirs[+b.dataset.i].path));
  document.querySelectorAll(".exFile").forEach(b => b.onclick = () => filePreviewModal(d.files[+b.dataset.i]));
  document.querySelectorAll(".exDelFile").forEach(b => b.onclick = () => exDeleteFile(d.files[+b.dataset.i]));
  document.querySelectorAll(".exDelDir").forEach(b => b.onclick = () => bulkModal(d.subdirs[+b.dataset.i].path, exAfterBulk, "tree"));
  $("exBulk") && ($("exBulk").onclick = () => bulkModal(d.path, exAfterBulk));
  $("exReview") && ($("exReview").onclick = () => { show("clean"); openFolder(d.path) });
  $("exInfo") && ($("exInfo").ontoggle = e => infoOpen = e.target.open);
}

function exAfterBulk(mode, r, target) {
  // if the Clean tab was on this folder, it no longer exists
  if (mode === "tree" && folder && (folder === target || folder.startsWith(target + SEP))) { folder = null; files = []; emptyViewer() }
  if (mode === "files" && folder === target) openFolder(target);
  updateStat(); renderFolders();
  toast(`${plural(r.trashed, "file")} went to the Trash (${fmt(r.freed_now)})` + (r.skipped ? ` · ${plural(r.skipped, "dangerous file")} kept` : ""), "ok", undoAction(r.undo));
  // if the current folder was deleted, go up one level
  explore(mode === "tree" && target === exPath ? exPath.split(SEP).slice(0, -1).join(SEP) || "." : exPath);
}

async function exDeleteFile(f, confirmed) {
  if (f.risk === "danger" && !confirmed) return confirmDanger(f, () => exDeleteFile(f, true));
  const r = await api("/api/trash", { folder: exPath, name: f.name });
  if (r.error) return toast("Error: " + r.error, "error");
  freed = r.freed; trashed++; setUndo(r.undo);
  const fo = report.folders.find(x => x.path === exPath);
  if (fo) { fo.size -= f.size; fo.count-- }
  if (folder === exPath) files = files.filter(x => x.name !== f.name);
  updateStat(); toast(`${f.name} went to the Trash`, "ok", undoAction(r.undo));
  explore(exPath);
}

function filePreviewModal(f, dir = exPath, onDel = () => exDeleteFile(f)) {
  const m = $("modal"), prev = previewHTML(f, dir);
  m.innerHTML = `<div class="bg-white dark:bg-slate-900 rounded-2xl p-5 max-w-3xl w-full shadow-xl fade-in">
    <div class="h-[46vh] grid place-items-center rounded-xl bg-slate-100 dark:bg-slate-800/60 overflow-hidden p-2">${prev}</div>
    <div class="mt-3 font-semibold break-all">${esc(f.name)}</div>
    <div class="text-sm text-slate-500 dark:text-slate-400">${fmt(f.size)} · ${new Date(f.mtime * 1000).toLocaleString()}</div>
    <div class="mt-3 rounded-xl border p-3 ${RISK[f.risk].ring}">${chip(f.risk, RISK[f.risk].label)}
      <ul class="mt-2 text-sm list-disc pl-5">${f.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul></div>
    <div class="flex gap-2 justify-end mt-4">
      <button id="pvClose" class="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm font-medium">Close</button>
      ${onDel ? `<button id="pvDel" class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-sm font-medium inline-flex items-center gap-1.5"><i data-lucide="trash-2" class="w-4 h-4"></i>Delete</button>` : ""}
    </div></div>`;
  m.classList.replace("hidden", "flex"); icons();
  const close = () => m.classList.replace("flex", "hidden");
  m.onclick = e => { if (e.target === m) close() };
  $("pvClose").onclick = close;
  $("pvDel") && ($("pvDel").onclick = () => { close(); onDel() });
}

/* ---------------- Duplicates ---------------- */
let dupData = null, dupSel = new Set(), dupShown = 40, dupMin = 1 << 20, dupTimer = null;
const DUP_SIZES = [[1, "Any size"], [100 << 10, "Larger than 100 KB"], [1 << 20, "Larger than 1 MB"],
                   [10 << 20, "Larger than 10 MB"], [100 << 20, "Larger than 100 MB"]];
const baseName = p => p.split(SEP).pop();
const dirOf = p => p.includes(SEP) ? p.slice(0, p.lastIndexOf(SEP)) : ".";

async function loadDups() {
  clearTimeout(dupTimer);
  if (!report) return renderDups();
  dupData = await api("/api/duplicates");
  // forget selections of files that are no longer in the list
  const alive = new Set((dupData.groups || []).flatMap(g => g.files.map(f => f.path)));
  dupSel = new Set([...dupSel].filter(p => alive.has(p)));
  if (!$("dups").hidden) renderDups();
  if (dupData.running) dupTimer = setTimeout(loadDups, 600);
}

async function startDups() {
  const r = await api("/api/duplicates", { min_size: dupMin });
  if (r.error) return toast(r.error, "error");
  dupSel.clear(); dupShown = 40; loadDups();
}

function dupGroupsByPath() {
  const m = new Map();
  (dupData?.groups || []).forEach(g => g.files.forEach(f => m.set(f.path, g)));
  return m;
}

function renderDups() {
  const card = "bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800";
  if (!report) {
    $("dups").innerHTML = `<div class="${card} p-10 text-center text-slate-500">Scan a folder first.</div>`;
    return;
  }
  const d = dupData || {}, groups = d.groups;
  const selSize = [...dupSel].reduce((a, p) => a + (dupGroupsByPath().get(p)?.size || 0), 0);
  const btn = "px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800 inline-flex items-center gap-1.5";
  let body = "";
  if (d.running) {
    const pct = d.total ? Math.round(d.done / d.total * 100) : 0;
    body = `<div class="${card} p-10 text-center fade-in">
      <i data-lucide="loader-2" class="w-10 h-10 mx-auto animate-spin text-indigo-500"></i>
      <p class="mt-4 font-medium">${esc(d.stage || "Searching…")}</p>
      <p class="text-sm text-slate-500 mt-1">${d.total ? `${d.done.toLocaleString()} of ${plural(d.total, "file")}` : "getting ready…"}</p>
      <div class="h-1.5 max-w-sm mx-auto mt-4 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden"><div class="h-full bg-indigo-500 transition-all" style="width:${pct}%"></div></div></div>`;
  } else if (d.error) {
    body = `<div class="bg-rose-50 dark:bg-rose-500/10 border border-rose-300 dark:border-rose-700 rounded-2xl p-6 text-rose-800 dark:text-rose-300">
      <p class="font-semibold">Error while searching for duplicates</p><p class="text-sm mt-1">${esc(d.error)}</p></div>`;
  } else if (!groups) {
    body = `<div class="${card} p-10 text-center text-slate-500 dark:text-slate-400 fade-in">
      <i data-lucide="copy" class="w-12 h-12 mx-auto mb-3 opacity-40"></i>
      <p class="font-medium">Find repeated files</p>
      <p class="text-sm mt-1 max-w-md mx-auto">Cleaner compares file contents, not just names. Files with different names but the same content show up too.</p></div>`;
  } else if (!groups.length) {
    body = `<div class="${card} p-10 text-center fade-in">
      <div class="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-500/15 grid place-items-center mx-auto mb-4"><i data-lucide="check" class="w-8 h-8 text-emerald-600 dark:text-emerald-400"></i></div>
      <p class="text-lg font-semibold">No duplicate files</p><p class="text-sm text-slate-500 mt-1">at this minimum size.</p></div>`;
  } else {
    body = `
      <div class="grid sm:grid-cols-3 gap-4 mb-5 fade-in">
        ${kpi("copy", "Groups of identical files", d.group_count.toLocaleString())}
        ${kpi("files", "Extra copies", d.extra_files.toLocaleString(), "keeping one of each")}
        ${kpi("leaf", "Can be freed", fmt(d.wasted), "if you delete every extra copy", "text-emerald-600 dark:text-emerald-400")}
      </div>
      <div class="${card} p-3 mb-4 flex flex-wrap items-center gap-2 sticky top-[68px] z-10">
        <span class="text-sm text-slate-500 dark:text-slate-400 mr-1">Mark automatically:</span>
        <button class="${btn}" id="dupOld"><i data-lucide="history" class="w-4 h-4"></i>Keep the oldest</button>
        <button class="${btn}" id="dupNew"><i data-lucide="sparkle" class="w-4 h-4"></i>Keep the newest</button>
        ${dupSel.size ? `<button class="${btn}" id="dupNone"><i data-lucide="x" class="w-4 h-4"></i>Unmark all</button>` : ""}
        <button id="dupDel" ${dupSel.size ? "" : "disabled"} class="ml-auto px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-1.5">
          <i data-lucide="trash-2" class="w-4 h-4"></i>Delete ${dupSel.size} marked${dupSel.size ? " · " + fmt(selSize) : ""}</button>
      </div>
      <div class="space-y-3">${groups.slice(0, dupShown).map(dupGroup).join("")}</div>
      ${groups.length > dupShown ? `<div class="text-center mt-4"><button id="dupMore" class="${btn}">Show ${Math.min(40, groups.length - dupShown)} more of ${plural(groups.length - dupShown, "group")}</button></div>` : ""}
      ${d.group_count > groups.length ? `<p class="text-xs text-center text-slate-500 mt-3">Showing the ${groups.length} groups that take up the most space.</p>` : ""}`;
  }
  $("dups").innerHTML = `
    <div class="${card} p-5 mb-5 flex flex-wrap items-center gap-3 fade-in">
      <div class="flex-1 min-w-[220px]">
        <h2 class="font-semibold flex items-center gap-2"><i data-lucide="copy" class="w-4 h-4 text-slate-400"></i>Duplicate files</h2>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">The same content in more than one place, inside ${esc(report.root)}. You choose which copies to delete; at least one of each is always kept.</p>
      </div>
      <select id="dupMin" class="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-sm" ${d.running ? "disabled" : ""}>
        ${DUP_SIZES.map(([v, l]) => `<option value="${v}" ${v === dupMin ? "selected" : ""}>${l}</option>`).join("")}
      </select>
      <button id="dupGo" ${d.running ? "disabled" : ""} class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-1.5">
        <i data-lucide="search" class="w-4 h-4"></i>${groups ? "Search again" : "Find duplicates"}</button>
    </div>${body}`;
  icons();
  $("dupMin").onchange = e => dupMin = +e.target.value;
  $("dupGo").onclick = startDups;
  if (!groups?.length) return;
  $("dupOld").onclick = () => autoSelect("old");
  $("dupNew").onclick = () => autoSelect("new");
  $("dupNone") && ($("dupNone").onclick = () => { dupSel.clear(); renderDups() });
  $("dupMore") && ($("dupMore").onclick = () => { dupShown += 40; renderDups() });
  $("dupDel").onclick = deleteDups;
  const byPath = dupGroupsByPath();
  document.querySelectorAll(".dupCk").forEach(c => c.onchange = () => {
    const g = byPath.get(c.dataset.p);
    if (c.checked && g.files.every(f => f.path === c.dataset.p || dupSel.has(f.path))) {
      c.checked = false;
      return toast("Keep at least one copy of each file.", "info");
    }
    c.checked ? dupSel.add(c.dataset.p) : dupSel.delete(c.dataset.p);
    renderDups();
  });
  document.querySelectorAll(".dupEye").forEach(b => b.onclick = () => {
    const g = byPath.get(b.dataset.p), f = g.files.find(x => x.path === b.dataset.p);
    filePreviewModal({ ...f, name: baseName(f.path), size: g.size }, dirOf(f.path), null);
  });
}

function dupGroup(g) {
  const kept = g.files.filter(f => !dupSel.has(f.path)).length;
  return `<div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
      <div class="text-sm font-semibold flex items-center gap-2"><i data-lucide="${fileIcon(g.files[0].mime)}" class="w-4 h-4 text-slate-400"></i>
        ${g.files.length} copies · ${fmt(g.size)} each</div>
      <div class="text-xs text-slate-500 dark:text-slate-400">${kept === 1 ? "1 copy stays" : `${kept} copies stay`} · extra copies take ${fmt(g.size * (g.files.length - 1))}</div>
    </div>
    ${g.files.map(f => `
      <div class="flex items-center gap-3 px-2 py-1.5 rounded-lg ${dupSel.has(f.path) ? "bg-rose-50 dark:bg-rose-500/10" : "hover:bg-slate-50 dark:hover:bg-slate-800/60"}">
        <input type="checkbox" class="dupCk w-4 h-4 accent-rose-600 shrink-0" data-p="${esc(f.path)}" ${dupSel.has(f.path) ? "checked" : ""} aria-label="Mark for deletion">
        <span class="truncate text-sm flex-1 min-w-0 ${dupSel.has(f.path) ? "line-through text-slate-400" : ""}" style="direction:rtl;text-align:left" title="${esc(f.path)}">&lrm;${esc(f.path)}&lrm;</span>
        <span class="text-xs text-slate-500 dark:text-slate-400 shrink-0 hidden sm:inline">${new Date(f.mtime * 1000).toLocaleDateString()}</span>
        <span class="shrink-0" title="${esc(f.reasons.join(" · "))}">${chip(f.risk)}</span>
        <button class="dupEye p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 shrink-0" data-p="${esc(f.path)}" title="Preview"><i data-lucide="eye" class="w-4 h-4"></i></button>
      </div>`).join("")}
  </div>`;
}

// mark every copy but one (the oldest or the newest); never marks dangerous files
function autoSelect(which) {
  dupSel.clear();
  for (const g of dupData.groups) {
    const byDate = [...g.files].sort((a, b) => a.mtime - b.mtime);
    const keep = which === "old" ? byDate[0] : byDate[byDate.length - 1];
    g.files.forEach(f => { if (f !== keep && f.risk !== "danger") dupSel.add(f.path) });
  }
  renderDups();
}

async function deleteDups(confirmed) {
  const byPath = dupGroupsByPath(), paths = [...dupSel];
  const danger = paths.map(p => byPath.get(p)?.files.find(f => f.path === p)).filter(f => f?.risk === "danger");
  if (danger.length && confirmed !== true) {
    return confirmDanger({ name: `${plural(danger.length, "marked file")}`, reasons: [...new Set(danger.flatMap(f => f.reasons))] },
                         () => deleteDups(true));
  }
  const b = $("dupDel"); b.disabled = true; b.textContent = "Deleting…";
  const r = await api("/api/trash_paths", { paths });
  if (r.error) { toast("Error: " + r.error, "error"); return renderDups() }
  freed = r.freed; trashed += r.trashed; setUndo(r.undo);
  upsertFolders(r.folders); updateStat(); renderFolders();
  dupSel.clear();
  await refreshViews();
  toast(`${plural(r.trashed, "copy", "copies")} went to the Trash (${fmt(r.freed_now)})` + (r.errors.length ? ` · ${r.errors[0]}` : ""), "ok", undoAction(r.undo));
}

// action: { label, fn } shows a button in the notice (e.g. "Undo")
function toast(msg, kind = "ok", action = null) {
  const t = $("toast");
  const ic = { ok: "check-circle-2", error: "x-circle", info: "info" }[kind];
  t.innerHTML = `<div class="flex items-center gap-3 px-4 py-2.5 rounded-xl shadow-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-sm fade-in max-w-[calc(100vw-2rem)]">
    <i data-lucide="${ic}" class="w-4 h-4 shrink-0"></i><span class="min-w-0 break-words">${esc(msg)}</span>
    ${action ? `<button id="toastAct" class="shrink-0 font-semibold text-indigo-300 dark:text-indigo-600 hover:underline">${esc(action.label)}</button>` : ""}</div>`;
  t.classList.remove("hidden"); icons();
  if (action) $("toastAct").onclick = () => { t.classList.add("hidden"); action.fn() };
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), action ? 7000 : 2600);
}

/* ---------------- Undo ---------------- */
const undoAction = u => u && { label: "Undo", fn: () => undo(u.id) };

function setUndo(u) {
  lastUndo = u || null;
  const b = $("undoBtn");
  b.classList.toggle("hidden", !lastUndo); b.classList.toggle("inline-flex", !!lastUndo);
  b.title = lastUndo ? `Restore from the Trash: ${lastUndo.label} (Ctrl+Z)` : "";
}

// update (or add) folders in the Clean screen list with the summary from the server
function upsertFolders(list) {
  if (!report || !list) return;
  for (const e of list) {
    const i = report.folders.findIndex(f => f.path === e.path);
    if (i >= 0) report.folders[i] = e; else report.folders.push(e);
  }
  report.folders.sort((a, b) => b.size - a.size);
}

// reload the open screens after files changed (deleted or restored)
async function refreshViews(restored = []) {
  if (folder) {
    const cur = files[idx]?.name;
    files = await api("/api/files?folder=" + encodeURIComponent(folder));
    if (files.error) files = [];
    const back = files.findIndex(f => restored.includes(relOf(folder, f.name)));
    const same = files.findIndex(f => f.name === cur);
    idx = back >= 0 ? back : same >= 0 ? same : Math.min(idx, files.length);
    if (!$("clean").hidden) renderViewer();
  }
  if (!$("explore").hidden) explore(exPath);
  if (dupData?.groups) loadDups();
}

async function undo(id) {
  if (!lastUndo && id === undefined) return;
  const r = await api("/api/undo", id ? { id } : {});
  if (r.error) { if ("undo" in r) setUndo(r.undo); return toast("Error: " + r.error, "error") }
  freed = r.freed; trashed = r.trashed; setUndo(r.undo);
  history = history.filter(h => h.op !== r.undone);
  upsertFolders(r.folders);
  updateStat(); renderFolders();
  await refreshViews(r.paths);
  toast(`${plural(r.restored, "item")} restored from the Trash` + (r.errors.length ? ` · ${r.errors[0]}` : ""));
}

document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || $("modal").classList.contains("flex")) return;
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z") { e.preventDefault(); return undo() }
  if ($("clean").hidden) return;
  if (e.key === "ArrowLeft" || e.key === "Delete") del();
  else if (e.key === "ArrowRight") keep();
  else if (e.key === "Backspace") back();
});

function updateStat() {
  $("stat").innerHTML = report ? `<i data-lucide="leaf" class="w-4 h-4 text-emerald-500"></i>Freed: <b class="text-slate-700 dark:text-slate-200">${fmt(freed)}</b>` : "";
  icons();
}

function show(tab) {
  for (const t of ["report", "explore", "clean", "dups"]) $(t).hidden = tab !== t;
  document.querySelectorAll(".tab").forEach(b => b.className = "tab px-4 py-1.5 rounded-lg text-sm font-medium flex items-center gap-1.5 " +
    (b.dataset.tab === tab ? "bg-white dark:bg-slate-700 shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"));
  if (tab === "report") renderReport();
  if (tab === "explore" && report) explore(exPath);
  if (tab === "dups") dupData ? renderDups() : loadDups();
}
document.querySelectorAll(".tab").forEach(b => b.onclick = () => show(b.dataset.tab));
$("folderSearch").oninput = renderFolders;
$("undoBtn").onclick = () => undo();
dark.addEventListener("change", () => !$("report").hidden && renderReport());

async function poll() {
  const s = await api("/api/status");
  if (!$("root").value) $("root").value = s.report?.root || s.home;
  if (s.scanning) {
    $("report").innerHTML = `<div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-10 text-center">
      <i data-lucide="loader-2" class="w-10 h-10 mx-auto animate-spin text-indigo-500"></i>
      <p class="mt-4 font-medium">Scanning…</p><p class="text-sm text-slate-500 mt-1">${plural(s.progress, "file")} found</p></div>`;
    icons();
    return setTimeout(poll, 700);
  }
  report = s.report; freed = s.freed; trashed = s.trashed; folder = null; files = [];
  SEP = s.sep || "/"; setUndo(s.undo); dupData = null; dupSel.clear();
  if (!$("dups").hidden) loadDups();
  try {
    if (report && report.safe_total === undefined) throw new Error("the server is from an older version of the app. Stop it (Ctrl+C) and run it again");
    updateStat(); renderReport(); renderRiskFilter(); renderFolders(); emptyViewer();
  } catch (e) {
    $("report").innerHTML = `<div class="bg-rose-50 dark:bg-rose-500/10 border border-rose-300 dark:border-rose-700 rounded-2xl p-6 text-rose-800 dark:text-rose-300">
      <p class="font-semibold">Error showing the report</p><p class="text-sm mt-1">${esc(e.message)}</p></div>`;
    console.error(e);
  }
}
$("scanBtn").onclick = async () => {
  const r = await api("/api/scan", { root: $("root").value });
  if (r.error) return toast(r.error, "error");
  report = null; show("report"); poll();
};
show("report"); poll();
