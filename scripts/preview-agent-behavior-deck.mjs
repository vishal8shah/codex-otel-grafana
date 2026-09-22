import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const deckPath = resolve(import.meta.dirname, "..", "docs", "agent-behavior-demo-deck.html");
const port = Number(process.env.DECK_PREVIEW_PORT || 8765);

createServer(async (_request, response) => {
  try {
    const html = await readFile(deckPath);
    response.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    response.end(html);
  } catch {
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end("Deck preview unavailable.");
  }
}).listen(port, "127.0.0.1", () => {
  console.log(`Deck preview: http://127.0.0.1:${port}`);
});
