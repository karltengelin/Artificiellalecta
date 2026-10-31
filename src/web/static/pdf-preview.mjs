// Render the verified delivery itself, independently of browser PDF plug-ins.
import { getDocument, GlobalWorkerOptions } from "./pdfjs-6.4.299.min.mjs";

GlobalWorkerOptions.workerSrc = new URL("./pdfjs-worker-6.4.299.min.mjs", import.meta.url).href;
const previews = new WeakMap();

async function mount(root) {
  const status = root.querySelector("[data-pdf-status]");
  const canvas = root.querySelector("[data-pdf-canvas]");
  const scroll = root.querySelector("[data-pdf-scroll]");
  const previous = root.querySelector("[data-pdf-previous]");
  const next = root.querySelector("[data-pdf-next]");
  const zoom = root.querySelector("[data-pdf-zoom]");
  const pageLabel = root.querySelector("[data-pdf-page]");
  let pdf, loading, renderTask, observer;
  let pageNumber = 1, rendering = false, pending = false, destroyed = false;
  const controller = new AbortController();
  const state = { destroy() {
    if (destroyed) return;
    destroyed = true;
    controller.abort();
    observer?.disconnect();
    renderTask?.cancel();
    loading?.destroy();
  } };
  previews.set(root, state);

  function controls(busy) {
    previous.disabled = busy || pageNumber <= 1;
    next.disabled = busy || pageNumber >= pdf.numPages;
    zoom.disabled = busy;
  }

  async function paint() {
    if (destroyed) return;
    if (rendering) { pending = true; return; }
    rendering = true;
    controls(true);
    try {
      do {
        pending = false;
        const page = await pdf.getPage(pageNumber);
        if (destroyed) return;
        const width = Math.max(1, scroll.clientWidth - 24);
        const scale = zoom.value === "fit" ? width / page.getViewport({ scale: 1 }).width : Number(zoom.value);
        const viewport = page.getViewport({ scale });
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.ceil(viewport.width * pixelRatio);
        canvas.height = Math.ceil(viewport.height * pixelRatio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        canvas.hidden = false;
        renderTask = page.render({ canvasContext: canvas.getContext("2d"), viewport,
          transform: [pixelRatio, 0, 0, pixelRatio, 0, 0] });
        await renderTask.promise;
        if (destroyed) return;
        canvas.setAttribute("aria-label", `Rapport, sida ${pageNumber} av ${pdf.numPages}`);
        pageLabel.textContent = `Sida ${pageNumber} av ${pdf.numPages}`;
        status.hidden = true;
      } while (pending);
    } catch (error) {
      if (!destroyed) {
        canvas.hidden = true;
        status.hidden = false;
        status.textContent = "Rapportsidan kunde inte visas. Öppna PDF-länken ovan.";
      }
    } finally {
      rendering = false;
      if (!destroyed) controls(false);
    }
  }

  try {
    const url = new URL(root.dataset.pdfUrl, window.location.href);
    if (url.origin !== window.location.origin ||
        !/^\/(central\/fragor|team\/aktuarie)\/FLOW-\d{6}\/leverans\/\d+\/rapport\.pdf$/.test(url.pathname) ||
        url.search || url.hash) throw new Error("Invalid delivery URL");
    // The delivery endpoint checks both files against the flow's checksums.
    const response = await fetch(url, { cache: "no-store", credentials: "same-origin", signal: controller.signal });
    if (!response.ok) throw new Error("Delivery unavailable");
    loading = getDocument({ data: new Uint8Array(await response.arrayBuffer()),
      isEvalSupported: false, useWasm: false, useSystemFonts: true, stopAtErrors: true });
    pdf = await loading.promise;
    if (destroyed) return;
    previous.addEventListener("click", () => { if (pageNumber > 1) { pageNumber--; scroll.scrollTop = 0; paint(); } });
    next.addEventListener("click", () => { if (pageNumber < pdf.numPages) { pageNumber++; scroll.scrollTop = 0; paint(); } });
    zoom.addEventListener("change", () => paint());
    let width = root.clientWidth;
    observer = new ResizeObserver(() => {
      if (root.clientWidth !== width) { width = root.clientWidth; paint(); }
    });
    observer.observe(root);
    await paint();
  } catch (error) {
    if (!destroyed) status.textContent = "Rapporten kunde inte läsas. Öppna PDF-länken ovan eller ladda om uppdraget.";
  }
}

export function mountPreviews() {
  document.querySelectorAll("[data-pdf-preview]").forEach(root => {
    if (!previews.has(root)) mount(root);
  });
}

document.addEventListener("htmx:beforeCleanupElement", event => {
  const element = event.detail.elt;
  // HTMX also emits cleanup events for text nodes during body replacement.
  if (element?.nodeType !== 1) return;
  if (element.matches("[data-pdf-preview]")) previews.get(element)?.destroy();
  element.querySelectorAll("[data-pdf-preview]").forEach(root => previews.get(root)?.destroy());
});
