import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const deckPath = resolve(root, "docs", "agent-behavior-demo-deck.html");
const assets = {
  "__IMG_BEHAVIOR__": resolve(root, "docs", "assets", "dashboard-walkthrough", "agent-behavior-security.png"),
  "__IMG_COMMAND__": resolve(root, "docs", "assets", "dashboard-walkthrough", "command-center.png"),
  "__IMG_LOKI__": resolve(root, "docs", "assets", "dashboard-walkthrough", "loki-events.png")
};

let html = await readFile(deckPath, "utf8");
for (const [token, imagePath] of Object.entries(assets)) {
  if (!html.includes(token)) continue;
  const encoded = (await readFile(imagePath)).toString("base64");
  html = html.replaceAll(token, `data:image/png;base64,${encoded}`);
}
await writeFile(deckPath, html, "utf8");
