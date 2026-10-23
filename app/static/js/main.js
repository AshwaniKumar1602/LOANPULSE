// LoanPulse Main Client JS - Theme & Interactivity

document.addEventListener("DOMContentLoaded", () => {
  // 1. Dark Mode Management
  const themeToggleBtn = document.getElementById("theme-toggle");
  const htmlEl = document.documentElement;

  // Initialize theme from localStorage or system preference
  if (
    localStorage.getItem("loanpulse_theme") === "dark" ||
    (!("loanpulse_theme" in localStorage) &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)
  ) {
    htmlEl.classList.add("dark");
  } else {
    htmlEl.classList.remove("dark");
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => {
      if (htmlEl.classList.contains("dark")) {
        htmlEl.classList.remove("dark");
        localStorage.setItem("loanpulse_theme", "light");
      } else {
        htmlEl.classList.add("dark");
        localStorage.setItem("loanpulse_theme", "dark");
      }
    });
  }

  // 2. Mobile Menu Toggle
  const mobileMenuBtn = document.getElementById("mobile-menu-btn");
  const mobileMenu = document.getElementById("mobile-menu");
  if (mobileMenuBtn && mobileMenu) {
    mobileMenuBtn.addEventListener("click", () => {
      mobileMenu.classList.toggle("hidden");
    });
  }

  // 3. Auto dismiss flash alerts
  const flashAlerts = document.querySelectorAll(".flash-alert");
  flashAlerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = "opacity 0.5s ease";
      alert.style.opacity = "0";
      setTimeout(() => alert.remove(), 500);
    }, 6000);
  });
});
