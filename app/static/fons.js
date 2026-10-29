(() => {
  const form = document.querySelector("#generate-form");
  const info = document.querySelector("#generate-info");
  const box = document.querySelector("#candidates");
  const empty = document.querySelector("#empty-candidates");
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  let shown = "";

  function render(status) {
    const pending = status.jobs.filter((job) => !job.finished);
    const failed = status.jobs.filter((job) => job.finished && job.error).slice(-1);
    const waiting = pending.reduce((sum, job) => sum + job.total - job.done, 0);
    info.textContent = pending.length
      ? `Generant… ${waiting} ${waiting === 1 ? "imatge pendent" : "imatges pendents"} (cada una pot tardar uns segons o un minut).`
      : failed.length ? failed[0].error : "";
    const key = JSON.stringify(status.candidates.map((c) => c.id)) + waiting;
    if (key === shown) return;
    shown = key;
    empty.hidden = status.candidates.length > 0 || waiting > 0;
    const placeholders = Array.from({length: waiting}, () => `<figure><div class="placeholder">Generant…</div><figcaption><span class="muted">Esperant Forge</span></figcaption></figure>`);
    box.innerHTML = placeholders.join("") + status.candidates.map((c) => `
      <figure data-id="${esc(c.id)}">
        <img src="${esc(c.image_url)}" alt="Opció de ${esc(c.theme)}" loading="lazy">
        <figcaption>
          <span class="muted">${esc(c.theme)}${c.model ? ` · ${esc(c.model)}` : ""}</span>
          <span class="candidate-actions">
            <button type="button" class="keep" data-action="guardar">Guardar</button>
            <button type="button" class="secondary" data-action="descartar">Descartar</button>
          </span>
        </figcaption>
      </figure>`).join("");
  }

  async function refresh() {
    try {
      const response = await fetch("/api/fons", {cache: "no-store"});
      if (response.ok) {
        const status = await response.json();
        render(status);
        const busy = status.jobs.some((job) => !job.finished);
        setTimeout(refresh, busy ? 3000 : 20000);
        return;
      }
    } catch { /* es torna a provar */ }
    setTimeout(refresh, 10000);
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const response = await fetch("/api/fons/generar", {method: "POST", body: new FormData(form)});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Error");
      info.textContent = "Enviat a Forge…";
      shown = "";
      setTimeout(refresh, 800);
    } catch (error) {
      info.textContent = `No s'ha pogut començar: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });

  box?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const figure = button.closest("figure");
    figure.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    const response = await fetch(`/api/fons/opcions/${figure.dataset.id}/${button.dataset.action}`, {method: "POST"});
    if (response.ok && button.dataset.action === "guardar") {
      // Recarrega per veure'l en «Fons guardats».
      window.location.reload();
      return;
    }
    shown = "";
    refresh();
  });

  refresh();
})();
