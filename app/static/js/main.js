// LoanPulse Main Client JS — Theme, Modal & Accessibility Handlers

// Global modal helpers
window.openModal = function (modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.firstElementChild?.classList.add("modal-animate-in");
  document.body.classList.add("overflow-hidden");
};

window.closeModal = function (modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.add("hidden");
  document.body.classList.remove("overflow-hidden");
};

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

  // 3. Modal Escape key and backdrop dismissal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const openModals = document.querySelectorAll('[role="dialog"]:not(.hidden)');
      openModals.forEach((modal) => {
        window.closeModal(modal.id);
      });
    }
  });

  document.querySelectorAll('[role="dialog"]').forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        window.closeModal(modal.id);
      }
    });
  });

  // 4. Auto dismiss flash alerts after 6 seconds
  const flashAlerts = document.querySelectorAll(".flash-alert");
  flashAlerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = "opacity 0.4s ease, transform 0.4s ease";
      alert.style.opacity = "0";
      alert.style.transform = "translateY(-6px)";
      setTimeout(() => alert.remove(), 400);
    }, 6000);
  });
});
