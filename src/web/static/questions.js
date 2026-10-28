document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-question-start]");
  if (!form) return;
  form.querySelector("button[type=submit]").disabled = true;
  form.querySelector("[data-question-progress]").hidden = false;
});
