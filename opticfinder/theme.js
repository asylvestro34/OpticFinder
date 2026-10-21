"use strict";

(() => {
  const key = "opticfinder-theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = null;
  let toggle;

  function readPreference() {
    try {
      const value = window.localStorage.getItem(key);
      return value === "light" || value === "dark" ? value : null;
    } catch (error) {
      console.warn("Theme preference could not be read; using the system theme.", error);
      return null;
    }
  }

  function applyTheme() {
    const theme = preference || (system.matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    if (toggle) {
      toggle.querySelector(".theme-label").textContent = theme === "dark" ? "Dark" : "Light";
      toggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
    }
  }

  preference = readPreference();
  applyTheme();
  system.addEventListener("change", applyTheme);
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) {
      preference = readPreference();
      applyTheme();
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    toggle = document.querySelector(".theme-toggle");
    if (!toggle) return;
    toggle.hidden = false;
    applyTheme();
    toggle.addEventListener("click", () => {
      preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme();
      try {
        window.localStorage.setItem(key, preference);
      } catch (error) {
        console.warn("Theme preference could not be saved; the theme will apply to this page only.", error);
      }
    });
  });
})();
