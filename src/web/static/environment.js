/* Miljöval gäller bara den här fliken. Inga formulärdata lagras utanför sidan. */
(() => {
  const originals = new WeakMap();
  const writes = new Set();
  let switching = false;

  const isDraftForm = form => form.method.toLowerCase() === "post" && !form.hasAttribute("data-environment-picker");
  const snapshot = form => JSON.stringify(Array.from(new FormData(form), ([key, value]) => [key, typeof value === "string" ? value : value.name]));
  function captureForms() {
    for (const form of document.forms) {
      if (isDraftForm(form) && !originals.has(form)) originals.set(form, snapshot(form));
    }
  }
  function hasDrafts() {
    return Array.from(document.forms).some(form => isDraftForm(form) && originals.has(form) && originals.get(form) !== snapshot(form));
  }
  function confirmDiscard() {
    const dialog = document.querySelector("[data-environment-confirm]");
    return new Promise(resolve => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "discard"), { once: true });
      dialog.returnValue = "cancel";
      dialog.showModal();
    });
  }
  document.addEventListener("click", event => {
    const decision = event.target.closest("[data-environment-decision]");
    if (decision) decision.closest("dialog").close(decision.dataset.environmentDecision);
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", captureForms, { once: true });
  else captureForms();
  document.addEventListener("htmx:load", captureForms);
  document.addEventListener("htmx:beforeRequest", event => {
    if (String(event.detail.requestConfig?.verb).toLowerCase() === "post") writes.add(event.detail.xhr);
  });
  document.addEventListener("htmx:afterRequest", event => writes.delete(event.detail.xhr));

  document.addEventListener("submit", async event => {
    const picker = event.target;
    if (!picker.matches("[data-environment-picker]")) return;
    event.preventDefault();
    if (switching) return;
    const select = picker.elements.namedItem("database");
    const message = picker.querySelector("[data-environment-message]");
    const show = text => { message.textContent = text; message.hidden = false; };
    const restore = () => { select.value = picker.dataset.currentDatabase; };
    if (select.value === picker.dataset.currentDatabase) { show("Du använder redan den här miljön."); return; }
    if (writes.size) { restore(); show("Vänta tills den pågående ändringen eller agentkörningen är klar innan du byter miljö."); return; }
    if (hasDrafts() && !await confirmDiscard()) {
      restore();
      return;
    }
    const body = new FormData(picker);
    const button = picker.querySelector("button[type=submit]");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    switching = true;
    select.disabled = button.disabled = true;
    show("Kontrollerar och öppnar målmiljön …");
    try {
      const response = await fetch(picker.action, {
        method: "POST", body, headers: { Accept: "application/json" }, credentials: "same-origin",
        redirect: "error", signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "Målmiljön kunde inte öppnas.");
      window.location.assign(result.url);
    } catch (error) {
      restore();
      show(error.name === "AbortError" ? "Målmiljön svarade inte i tid. Du är kvar här; försök igen." : error.message);
    } finally {
      clearTimeout(timeout);
      switching = false;
      select.disabled = button.disabled = false;
    }
  });
})();
