import { cp, mkdir, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// npm's lockfile verifies the upstream archive. Copy matching data and licenses;
// the browser fetches only the resources needed by the currently rendered page.
const source = dirname(
  fileURLToPath(import.meta.resolve("pdfjs-dist/package.json")),
);
const { version } = JSON.parse(
  await readFile(join(source, "package.json"), "utf8"),
);
const target = fileURLToPath(
  new URL(`../public/pdfjs-assets/${version}/`, import.meta.url),
);
await mkdir(target, { recursive: true });
for (const name of ["cmaps", "standard_fonts", "wasm", "iccs", "LICENSE"]) {
  await cp(join(source, name), join(target, name), { recursive: true });
}
console.log(`Prepared local PDF.js ${version} resources and licenses.`);
