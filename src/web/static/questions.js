document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-question-start]");
  if (!form) return;
  form.querySelector("button[type=submit]").disabled = true;
  form.querySelector("[data-question-progress]").hidden = false;
});

function mountReportPreviews() {
  if (document.querySelector("[data-pdf-preview]")) {
    import("/static/pdf-preview.mjs").then(module => module.mountPreviews()).catch(() => {
      document.querySelectorAll("[data-pdf-status]").forEach(status => {
        status.textContent = "Förhandsvisningen kunde inte laddas. Öppna PDF-länken ovan.";
      });
    });
  }
}

document.addEventListener("htmx:load", mountReportPreviews);
mountReportPreviews();
