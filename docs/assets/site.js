const pricing = {
  "gpt-5.5 standard": { input: 5, cached: 0.5, output: 30 },
  "gpt-5.4 standard": { input: 2.5, cached: 0.25, output: 15 },
  "gpt-5.4-mini standard": { input: 0.75, cached: 0.075, output: 4.5 },
  "gpt-5.3-codex standard": { input: 1.75, cached: 0.175, output: 14 },
  "local model": { input: 0, cached: 0, output: 0 }
};

const formatMoney = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: value < 10 ? 4 : 2 }).format(value);

function numberValue(id) {
  const value = Number(document.getElementById(id)?.value || 0);
  return Number.isFinite(value) ? value : 0;
}

function calculateCost() {
  const model = document.getElementById("model")?.value || "gpt-5.3-codex standard";
  const rates = pricing[model] || pricing["gpt-5.3-codex standard"];
  const runs = numberValue("runs");
  const input = numberValue("inputTokens");
  const cached = numberValue("cachedTokens");
  const output = numberValue("outputTokens");
  const regularInput = Math.max(input - cached, 0);
  const perRun = ((regularInput * rates.input) + (cached * rates.cached) + (output * rates.output)) / 1_000_000;
  const daily = perRun * runs;
  const monthly = daily * 30;
  const cacheSavings = ((cached * rates.input) - (cached * rates.cached)) / 1_000_000 * runs;

  document.getElementById("perRunCost").textContent = formatMoney(perRun);
  document.getElementById("dailyCost").textContent = formatMoney(daily);
  document.getElementById("monthlyCost").textContent = formatMoney(monthly);
  document.getElementById("cacheSavings").textContent = formatMoney(Math.max(cacheSavings, 0));
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
  const links = Array.from(document.querySelectorAll(".nav-link[href^='#']"));
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  const update = () => {
    let current = sections[0]?.id;
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top < 160) current = section.id;
    });
    links.forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href") === `#${current}`);
    });
  };

  document.addEventListener("scroll", update, { passive: true });
  update();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#model,#runs,#inputTokens,#cachedTokens,#outputTokens")
    .forEach((element) => element.addEventListener("input", calculateCost));
  setupSearch();
  setupNavState();
  calculateCost();
});
