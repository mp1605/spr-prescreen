import { build } from "vite";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const directory = await mkdtemp(join(tmpdir(), "spr-ui-contract-"));
try {
  await build({
    configFile: false,
    logLevel: "silent",
    esbuild: { jsx: "automatic" },
    ssr: { noExternal: true },
    build: {
      target: "node20",
      ssr: fileURLToPath(new URL("render-contracts.tsx", import.meta.url)),
      outDir: directory,
      rollupOptions: {
        output: { format: "es", entryFileNames: "contract.mjs" },
      },
    },
  });
  await import(pathToFileURL(join(directory, "contract.mjs")).href);
} finally {
  await rm(directory, { recursive: true, force: true });
}
