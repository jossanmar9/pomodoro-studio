(() => {
  const STEPS = ["BACKGROUND", "AUDIO", "RENDERING", "PUBLISHING"];
  const ACTIVE = new Set(["QUEUED", ...STEPS]);
  const box = document.querySelector("#runs");
  const form = document.querySelector("#auto-form");
  const go = document.querySelector("#go");

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const hours = (minutes) => (minutes % 60 ? `${minutes} min` : `${minutes / 60} h`);
  const clock = (seconds) => {
    if (seconds == null) return "";
    const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
    return h ? `${h} h ${m} min` : `${m} min`;
  };

  function stepBar(run) {
    const index = STEPS.indexOf(run.step);
    const finished = run.step === "DONE" ? STEPS.length : run.step === "DONE_LOCAL" ? 3 : -1;
    return `<div class="steps">${STEPS.map((_, i) => {
      const cls = i < index || i < finished ? "done" : i === index ? "now" : "";
      return `<i class="${cls}"></i>`;
    }).join("")}</div>`;
  }

  // Vídeos de 6 en 6, amb fletxes per a passar pàgina.
  const PER_PAGE = 6;
  let page = 0;
  let allRuns = [];
  const pager = document.querySelector("#pager");
  const pageInfo = document.querySelector("#page-info");
  const prev = document.querySelector("#page-prev");
  const next = document.querySelector("#page-next");
  const pages = () => Math.max(1, Math.ceil(allRuns.length / PER_PAGE));
  prev?.addEventListener("click", () => { if (page > 0) { page -= 1; draw(); } });
  next?.addEventListener("click", () => { if (page < pages() - 1) { page += 1; draw(); } });
  const day = (iso) => (iso ? iso.split("-").reverse().join("/") : "");

  function render(runs) {
    allRuns = runs || [];
    draw();
  }

  function draw() {
    const runs = allRuns;
    if (!runs.length) return;
    page = Math.min(page, pages() - 1);
    const first = page * PER_PAGE;
    if (pager) {
      pager.hidden = runs.length <= PER_PAGE;
      pageInfo.textContent = `${first + 1}–${Math.min(first + PER_PAGE, runs.length)} de ${runs.length}`;
      prev.disabled = page === 0;
      next.disabled = page >= pages() - 1;
    }
    box.innerHTML = runs.slice(first, first + PER_PAGE).map((run) => {
      let detail = "";
      if (run.step === "RENDERING" && run.progress != null) {
        detail = `${run.progress}%${run.eta ? ` · queden uns ${clock(run.eta)}` : ""}`;
      }
      const actions = [];
      if (ACTIVE.has(run.step) && run.step !== "PUBLISHING") actions.push(`<button type="button" class="mini secondary" data-cancel="${run.id}">Cancel·lar</button>`);
      if (run.video_url) actions.push(`<a href="${esc(run.video_url)}" target="_blank" rel="noopener">Veure a YouTube ↗</a>`);
      if (run.project_id) actions.push(`<a href="/projects/${run.project_id}">Fitxa del vídeo</a>`);
      if (!run.video_id && run.project_id && run.video_available && (run.step === "DONE_LOCAL" || (run.step === "FAILED" && /YouTube|Comprovació/.test(run.error || "")))) {
        const anyway = /^Comprovació/.test(run.error || "");
        actions.push(`<form action="/auto/${run.id}/publish" method="post"><button type="submit" class="mini">${anyway ? "Publicar igualment" : "Publicar ara"}</button></form>`);
      }
      if (run.short_missing && run.video_available) actions.push(`<form action="/auto/${run.id}/short" method="post"><button type="submit" class="mini">Fer el Short</button></form>`);
      if (run.reel_missing) actions.push(`<form action="/auto/${run.id}/reel" method="post"><button type="submit" class="mini">Fer el reel</button></form>`);
      if (run.instagram_media_id) actions.push(`<span class="muted">✓ Instagram</span>`);
      if (run.facebook_video_id) actions.push(`<span class="muted">✓ Facebook</span>`);
      if (run.delete_on && run.video_available) actions.push(`<span class="muted">El vídeo s'esborrarà de l'ordinador el ${esc(run.delete_on.split("-").reverse().join("/"))}</span>`);
      if (run.video_id && run.step === "DONE" && run.video_available) {
        actions.push(`<form action="/auto/${run.id}/publish" method="post" onsubmit="return confirm('Tornar a pujar este vídeo? Fes-ho només si YouTube l\\'ha eliminat.')"><input type="hidden" name="again" value="1"><button type="submit" class="mini secondary">Tornar a pujar</button></form>`);
      }
      const thumb = run.thumbnail_url ? `<img class="run-thumb" src="${esc(run.thumbnail_url)}" alt="" loading="lazy">` : `<div class="run-thumb empty"></div>`;
      return `<article class="run">
        ${thumb}
        <div class="run-body">
        <div class="run-head">
          <strong>${esc(run.theme)} <span class="muted">· ${esc(run.environment_label)} · ${hours(run.duration_minutes)} · ${esc(run.pomodoro)}</span></strong>
          <span class="run-step ${esc(run.step)}">${esc(run.step_label)}${detail ? ` · ${detail}` : ""}</span>
        </div>
        <small class="muted">#${run.id}${run.published_at ? ` · publicat el ${day(run.published_at)}` : ""}</small>
        ${stepBar(run)}
        ${run.message && !ACTIVE.has(run.step) ? `<span class="muted">${esc(run.message)}</span>` : ""}
        ${run.error ? `<span class="error">${esc(run.error)}</span>` : ""}
        ${actions.length ? `<div class="run-actions">${actions.join("")}</div>` : ""}
        </div>
      </article>`;
    }).join("");
  }

  box?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-cancel]");
    if (!button || !confirm("Cancel·lar este vídeo?")) return;
    button.disabled = true;
    button.textContent = "Cancel·lant…";
    const response = await fetch(`/auto/${button.dataset.cancel}/cancel`, {method: "POST"});
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      alert(result.detail || "No s'ha pogut cancel·lar");
    }
    refresh();
  });

  async function refresh() {
    try {
      const response = await fetch("/api/auto", {cache: "no-store"});
      if (!response.ok) return;
      const data = await response.json();
      render(data.runs);
      const pending = showShutdown(data.shutdown);
      const busy = data.runs.some((run) => ACTIVE.has(run.step));
      setTimeout(refresh, pending ? 1000 : busy ? 3000 : 15000);
    } catch {
      setTimeout(refresh, 10000);
    }
  }

  // Apagada pendent: compte enrere i botó per cancel·lar-la.
  const banner = document.querySelector("#shutdown-banner");
  const bannerText = document.querySelector("#shutdown-text");
  function showShutdown(state) {
    if (!banner) return false;
    if (state?.scheduled) {
      const m = Math.floor(state.seconds_left / 60), s = String(state.seconds_left % 60).padStart(2, "0");
      bannerText.textContent = `${state.reason}. L'ordinador s'apagarà d'ací ${m}:${s}.`;
      banner.hidden = false;
      document.querySelector("#shutdown-cancel").hidden = false;
      return true;
    }
    if (state?.error) {
      bannerText.textContent = state.error;
      banner.hidden = false;
      document.querySelector("#shutdown-cancel").hidden = true;
      return false;
    }
    banner.hidden = true;
    return false;
  }
  document.querySelector("#shutdown-cancel")?.addEventListener("click", async () => {
    await fetch("/api/shutdown/cancel", {method: "POST"});
    banner.hidden = true;
  });

  render(window.__RUNS__ || []);
  refresh();

  form?.addEventListener("submit", () => {
    go.disabled = true;
    go.textContent = "Enviant…";
  });

  const publish = form?.querySelector('input[name="publish"]');
  const syncLabel = () => { go.textContent = publish.checked ? "Generar i publicar" : "Generar el vídeo"; };
  publish?.addEventListener("change", syncLabel);

  // Mostra d'àudio: el vídeo reutilitza els sons que s'han escoltat.
  const previewBtn = document.querySelector("#preview");
  const reshuffle = document.querySelector("#reshuffle");
  const audio = document.querySelector("#preview-audio");
  const info = document.querySelector("#preview-info");
  const files = document.querySelector("#ambience-files");
  const musicFile = document.querySelector("#music-file");
  const forgetSounds = () => { files.value = ""; musicFile.value = ""; reshuffle.hidden = true; info.textContent = ""; audio.hidden = true; audio.removeAttribute("src"); };

  async function preview(keep) {
    const data = new FormData();
    for (const name of ["theme", "format", "environment", "noise", "ambience_level", "music", "music_style", "music_level", "chime"]) {
      const field = form.querySelector(`[name="${name}"]:checked, select[name="${name}"]`);
      if (field && !(field.type === "checkbox" && !field.checked)) data.set(name, field.value);
    }
    if (keep && files.value) data.set("ambience_files", files.value);
    if (keep && musicFile.value) data.set("music_file", musicFile.value);
    previewBtn.disabled = reshuffle.disabled = true;
    info.textContent = "Preparant la mostra…";
    try {
      const response = await fetch("/api/auto/preview", {method: "POST", body: data});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Error");
      files.value = result.files.join(",");
      musicFile.value = result.music || "";
      audio.src = result.url;
      audio.hidden = false;
      reshuffle.hidden = !result.files.length;
      const withChime = currentFormat() === "pomodoro" && form.chime?.checked;
      info.textContent = (result.sounds.length ? `Sons: ${result.sounds.join(" · ")}` : "") + (withChime ? " · campaneta als 10 s i als 20 s" : "") + ". El vídeo usarà estos mateixos sons.";
      audio.play().catch(() => {});
    } catch (error) {
      info.textContent = `No s'ha pogut fer la mostra: ${error.message}`;
    } finally {
      previewBtn.disabled = reshuffle.disabled = false;
    }
  }
  // Format: mostra només les opcions que li corresponen.
  const currentFormat = () => form?.querySelector('input[name="format"]:checked')?.value || "pomodoro";
  function applyFormat() {
    const format = currentFormat();
    form.querySelectorAll("[data-show-for]").forEach((el) => { el.hidden = !el.dataset.showFor.split(" ").includes(format); });
    form.querySelectorAll("[data-hide-for]").forEach((el) => { el.hidden = el.dataset.hideFor.split(" ").includes(format); });
    // La respiració té les seues duracions (en minuts): marca'n una de visible.
    const checked = form.querySelector('input[name="duration_minutes"]:checked');
    if (!checked || checked.closest("[hidden]")) {
      const first = format === "respiracio" ? form.querySelector("input[data-breath-duration]") : form.querySelector('input[name="duration_minutes"][value="120"]');
      if (first) first.checked = true;
    }
  }
  form?.querySelectorAll('input[name="format"], input[name="noise"]').forEach((el) => el.addEventListener("change", () => { applyFormat(); forgetSounds(); }));
  // Si ja s'ha escoltat una mostra, en canviar un volum o la música es torna a fer amb els mateixos sons.
  const replay = () => { if (audio.getAttribute("src")) preview(true); };
  form?.querySelectorAll('#ambience-level, #music-level, input[name="music"]').forEach((el) => el.addEventListener("change", replay));
  form?.querySelector("#music-style")?.addEventListener("change", () => { musicFile.value = ""; replay(); });
  // Amb pantalla negra no hi ha color que puga «respirar».
  const pulse = document.getElementById("noise-pulse");
  const syncPulse = () => {
    const black = form.querySelector('input[name="noise_screen"]:checked')?.value === "negre";
    pulse.hidden = black;
    if (black) pulse.querySelector("input").checked = false;
  };
  form?.querySelectorAll('input[name="noise_screen"]').forEach((el) => el.addEventListener("change", syncPulse));
  if (pulse) syncPulse();
  if (form) applyFormat();

  previewBtn?.addEventListener("click", () => preview(true));
  reshuffle?.addEventListener("click", () => { files.value = ""; preview(false); });
  form?.querySelectorAll('input[name="environment"]').forEach((el) => el.addEventListener("change", forgetSounds));

  // Temes: quadres per tipus, estació i festa; en prémer-ne un s'obrin davall els seus temes.
  const groupTiles = [...document.querySelectorAll("button.group-tile")];
  const panels = [...document.querySelectorAll(".theme-panel")];
  function showGroup(name, pickFirst) {
    groupTiles.forEach((tile) => { const on = tile.dataset.group === name; tile.classList.toggle("active", on); tile.setAttribute("aria-expanded", String(on)); });
    panels.forEach((panel) => { panel.hidden = panel.dataset.group !== name; });
    const panel = panels.find((p) => p.dataset.group === name);
    if (pickFirst && panel && !panel.querySelector('input[name="theme"]:checked')) {
      const first = panel.querySelectorAll('input[name="theme"]')[1] || panel.querySelector('input[name="theme"]');
      if (first) { first.checked = true; first.dispatchEvent(new Event("change", {bubbles: true})); }
    }
  }
  function syncGroup() {
    const checked = form?.querySelector('input[name="theme"]:checked');
    const panel = checked?.closest(".theme-panel");
    // Els temes de temporada es trien directament: es tanca el requadre obert.
    showGroup(panel ? panel.dataset.group : null, false);
  }
  form?.querySelectorAll(".group-tile.direct input").forEach((el) => el.addEventListener("change", syncGroup));
  groupTiles.forEach((tile) => tile.addEventListener("click", () => showGroup(tile.dataset.group, true)));
  syncGroup();

  // Suggeriments: «Fer-ho» marca el tema i l'entorn suggerits i baixa al formulari.
  document.querySelectorAll("[data-suggest-theme]").forEach((button) => button.addEventListener("click", () => {
    const pick = (name, value) => {
      const input = value && [...form.querySelectorAll(`input[name="${name}"]`)].find((el) => el.value === value);
      if (input) { input.checked = true; input.dispatchEvent(new Event("change", {bubbles: true})); }
    };
    pick("format", form.querySelector('input[name="format"]:checked')?.value === "soroll" ? "pomodoro" : null);
    pick("theme", button.dataset.suggestTheme);
    pick("environment", button.dataset.suggestEnvironment);
    syncGroup();
    form.scrollIntoView({behavior: "smooth"});
  }));

  // Música: recomanació segons el format, l'entorn i el tema (es marca la casella, però la pots canviar).
  const advice = document.querySelector("#music-advice");
  async function adviseMusic() {
    if (!advice || !form) return;
    const params = new URLSearchParams({
      format: currentFormat(),
      environment: form.querySelector('input[name="environment"]:checked')?.value || "",
      theme: form.querySelector('input[name="theme"]:checked')?.value || "",
    });
    try {
      const response = await fetch(`/api/auto/music-advice?${params}`, {cache: "no-store"});
      if (!response.ok) return;
      const result = await response.json();
      if (result.recommended === null) { advice.textContent = ""; return; }
      if (form.music) form.music.checked = result.recommended;
      advice.textContent = `· Recomanat: ${result.recommended ? `amb música (${result.style.toLowerCase()})` : "sense música"}. ${result.reason}`;
    } catch { /* sense recomanació */ }
  }
  form?.querySelectorAll('input[name="theme"], input[name="format"], input[name="environment"]').forEach((el) => el.addEventListener("change", adviseMusic));
  adviseMusic();

  // Fons: miniatures del tema triat. Primer els fets per al format i l'entorn triats.
  const picker = document.querySelector("#bg-picker");
  const BACKGROUNDS = window.__BACKGROUNDS__ || {};
  const labelOf = (name, value) => form?.querySelector(`input[name="${name}"][value="${CSS.escape(value)}"] + span`)?.firstChild?.textContent?.trim() || "";
  function renderBackgrounds() {
    if (!picker) return;
    const theme = form.querySelector('input[name="theme"]:checked')?.value || "";
    if (theme.startsWith("grup:")) {
      picker.innerHTML = `<p class="muted">Es triarà a l'atzar un tema de «${esc(theme.slice(5))}» i un dels seus fons.</p>`;
      return;
    }
    const format = currentFormat();
    const environment = form.querySelector('input[name="environment"]:checked')?.value || "";
    const previous = form.querySelector('input[name="background"]:checked')?.value || "";
    const score = (b) => (b.format === format ? 2 : 0) + (b.environment === environment ? 1 : 0);
    const items = [...(BACKGROUNDS[theme] || [])].sort((a, b) => score(b) - score(a));
    if (!items.length) {
      picker.innerHTML = `<p class="missing">Encara no hi ha cap fons de «${esc(theme)}». <a class="back" href="/fons#importar">Afegir-ne un</a></p>`;
      return;
    }
    const keep = items.some((b) => b.name === previous) ? previous : "";
    picker.innerHTML = `<label class="bg-option"><input type="radio" name="background" value="" ${keep ? "" : "checked"}><span class="random">🎲 A l'atzar<br><small>${items.length} fons</small></span></label>` +
      items.map((b) => {
        const tags = [b.format && labelOf("format", b.format), b.environment && labelOf("environment", b.environment)].filter(Boolean).join(" · ");
        return `<label class="bg-option" title="${esc(b.name)}"><input type="radio" name="background" value="${esc(b.name)}" ${b.name === keep ? "checked" : ""}><span style="background-image:url('${encodeURI(b.url)}')"><small>${esc(tags || "Qualsevol")}</small></span></label>`;
      }).join("");
  }
  form?.querySelectorAll('input[name="theme"], input[name="format"], input[name="environment"]').forEach((el) => el.addEventListener("change", renderBackgrounds));
  renderBackgrounds();

  document.querySelector("#random")?.addEventListener("click", () => {
    for (const name of ["theme", "environment", "noise"]) {
      const options = [...form.querySelectorAll(`input[name="${name}"]`)];
      options[Math.floor(Math.random() * options.length)].checked = true;
    }
    forgetSounds();
    syncGroup();
    renderBackgrounds();
    adviseMusic();
  });
})();
