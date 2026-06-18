function setupTheme() {
  const stored = localStorage.getItem("theme");
  const initial = stored || "dark";
  document.documentElement.dataset.theme = initial;

  const button = document.getElementById("themeToggle");
  const sync = () => {
    const isLight = document.documentElement.dataset.theme === "light";
    if (button) {
      button.setAttribute("aria-label", isLight ? "Switch to dark mode" : "Switch to light mode");
      button.textContent = isLight ? "\u2600" : "\u263e";
    }
  };

  if (button) {
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("theme", next);
      sync();
    });
  }

  sync();
}

function setupSearch() {
  const input = document.getElementById("docSearch");
  if (!input) return;
  input.addEventListener("input", () => {
    const term = input.value.trim().toLowerCase();
    document.querySelectorAll("[data-search]").forEach((node) => {
      const hit = node.textContent.toLowerCase().includes(term);
      node.style.display = !term || hit ? "" : "none";
    });
  });
}

function setupNavState() {
  const currentPath = location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll(".nav-link,.nav-sub").forEach((link) => {
    const href = link.getAttribute("href") || "";
    if (href === currentPath || (currentPath === "" && href === "index.html")) {
      link.classList.add("active");
    }
  });

  const anchorLinks = Array.from(document.querySelectorAll(".nav-link[href^='#'],.nav-sub[href^='#']"));
  const sections = anchorLinks
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  const update = () => {
    let current = sections[0]?.id;
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top < 170) current = section.id;
    });
    anchorLinks.forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href") === `#${current}`);
    });
  };

  document.addEventListener("scroll", update, { passive: true });
  update();
}

document.addEventListener("DOMContentLoaded", () => {
  setupTheme();
  setupSearch();
  setupNavState();
});
