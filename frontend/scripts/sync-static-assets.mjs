import { copyFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const assets = [
  {
    source: require.resolve("plotly.js-dist-min/plotly.min.js"),
    destination: resolve(frontendRoot, "public/vendor/plotly/plotly.min.js"),
  },
];

await Promise.all(
  assets.map(async ({ source, destination }) => {
    await mkdir(dirname(destination), { recursive: true });
    await copyFile(source, destination);
  }),
);
