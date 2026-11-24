try {
  document.documentElement.dataset.theme =
    localStorage.getItem("learn.theme") || "dark";
} catch {
  document.documentElement.dataset.theme = "dark";
}
