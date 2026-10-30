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

  function render(runs) {
    if (!runs.length) return;
    box.innerHTML = runs.map((run) => {
      let detail = "";
      if (run.step === "RENDERING" && run.progress != null) {
        detail = `${run.progress}%${run.eta ? ` · queden uns ${clock(run.eta)}` : ""}`;
      }
      const actions = [];
      if (run.video_url) actions.push(`<a href="${esc(run.video_url)}" target="_blank" rel="noopener">Veure a YouTube ↗</a>`);
      if (run.project_id) actions.push(`<a href="/projects/${run.project_id}">Fitxa del vídeo</a>`);
      if (!run.video_id && run.project_id && (run.step === "DONE_LOCAL" || (run.step === "FAILED" && /YouTube/.test(run.error || "")))) {
        actions.push(`<form action="/auto/${run.id}/publish" method="post"><button type="submit" class="mini">Publicar ara</button></form>`);
      }
      if (run.video_id && run.step === "DONE") {
        actions.push(`<form action="/auto/${run.id}/publish" method="post" onsubmit="return confirm('Tornar a pujar este vídeo? Fes-ho només si YouTube l\\'ha eliminat.')"><input type="hidden" name="again" value="1"><button type="submit" class="mini secondary">Tornar a pujar</button></form>`);
      }
      return `<article class="run">
        <div class="run-head">
          <strong>#${run.id} · ${esc(run.theme)} · ${esc(run.environment_label)} · ${hours(run.duration_minutes)} · ${esc(run.pomodoro)}</strong>
          <span class="run-step ${esc(run.step)}">${esc(run.step_label)}${detail ? ` · ${detail}` : ""}</span>
        </div>
        ${stepBar(run)}
        ${run.message && !ACTIVE.has(run.step) ? `<span class="muted">${esc(run.message)}</span>` : ""}
        ${run.error ? `<span class="error">${esc(run.error)}</span>` : ""}
        ${actions.length ? `<div class="run-actions">${actions.join("")}</div>` : ""}
      </article>`;
    }).join("");
  }

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
  const forgetSounds = () => { files.value = ""; reshuffle.hidden = true; info.textContent = ""; audio.hidden = true; audio.removeAttribute("src"); };

  async function preview(keep) {
    const data = new FormData();
    for (const name of ["format", "environment", "noise", "ambience_level", "music", "chime"]) {
      const field = form.querySelector(`[name="${name}"]:checked, select[name="${name}"]`);
      if (field && !(field.type === "checkbox" && !field.checked)) data.set(name, field.value);
    }
    if (keep && files.value) data.set("ambience_files", files.value);
    previewBtn.disabled = reshuffle.disabled = true;
    info.textContent = "Preparant la mostra…";
    try {
      const response = await fetch("/api/auto/preview", {method: "POST", body: data});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Error");
      files.value = result.files.join(",");
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
  }
  form?.querySelectorAll('input[name="format"], input[name="noise"]').forEach((el) => el.addEventListener("change", () => { applyFormat(); forgetSounds(); }));
  if (form) applyFormat();

  previewBtn?.addEventListener("click", () => preview(true));
  reshuffle?.addEventListener("click", () => { files.value = ""; preview(false); });
  form?.querySelectorAll('input[name="environment"]').forEach((el) => el.addEventListener("change", forgetSounds));

  document.querySelector("#random")?.addEventListener("click", () => {
    for (const name of ["theme", "environment", "noise"]) {
      const options = [...form.querySelectorAll(`input[name="${name}"]`)];
      options[Math.floor(Math.random() * options.length)].checked = true;
    }
    forgetSounds();
  });
})();
