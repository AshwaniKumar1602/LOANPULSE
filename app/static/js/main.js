// LoanPulse Main Client JS — Theme, Modal, Dropdown & Accessibility Handlers
// Memory-safe implementations (zero memory leaks, bounded scopes)

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

  // 2. User Profile Dropdown Controller (Memory-Safe)
  const userMenuBtn = document.getElementById("user-menu-btn");
  const userDropdownMenu = document.getElementById("user-dropdown-menu");

  if (userMenuBtn && userDropdownMenu) {
    userMenuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isExpanded = userMenuBtn.getAttribute("aria-expanded") === "true";
      userMenuBtn.setAttribute("aria-expanded", String(!isExpanded));
      userDropdownMenu.classList.toggle("hidden");
    });

    document.addEventListener("click", (e) => {
      if (!userDropdownMenu.contains(e.target) && !userMenuBtn.contains(e.target)) {
        userDropdownMenu.classList.add("hidden");
        userMenuBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  // 3. Mobile Navigation Drawer Toggle
  const mobileMenuBtn = document.getElementById("mobile-menu-btn");
  const mobileMenu = document.getElementById("mobile-menu");
  if (mobileMenuBtn && mobileMenu) {
    mobileMenuBtn.addEventListener("click", () => {
      mobileMenu.classList.toggle("hidden");
    });
  }

  // 4. Modal Escape key and backdrop dismissal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      // Close open modals
      const openModals = document.querySelectorAll('[role="dialog"]:not(.hidden)');
      openModals.forEach((modal) => {
        window.closeModal(modal.id);
      });
      // Close user dropdown if open
      if (userDropdownMenu && !userDropdownMenu.classList.contains("hidden")) {
        userDropdownMenu.classList.add("hidden");
        if (userMenuBtn) userMenuBtn.setAttribute("aria-expanded", "false");
      }
    }
  });

  document.querySelectorAll('[role="dialog"]').forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        window.closeModal(modal.id);
      }
    });
  });

  // 5. Auto dismiss flash alerts after 6 seconds
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
