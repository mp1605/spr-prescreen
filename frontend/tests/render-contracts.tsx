// Official phrases and numeric render contracts only. No paper corpus or sponsor data.
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { BatchSelection } from "../src/components/BatchSelection";
import {
  droppedFiles,
  uploadIssue,
  type SelectedUpload,
} from "../src/logic/uploads";
import type { AIStatus } from "../src/api/ai";

const selected: SelectedUpload = {
  id: 1,
  path: "format.pdf",
  file: { name: "format.pdf", size: 1024 } as File,
};
const ai: AIStatus = {
  available: true,
  models: [{ name: "local-model", digest: "a".repeat(64), bytes: 1024 }],
  revision: "format-contract",
  message: "Available",
  settings: {
    enabled: false,
    model: "local-model",
    model_digest: null,
    endpoint: "http://127.0.0.1:11434",
    timeout_seconds: 20,
    context_tokens: 32768,
    max_output_tokens: 2048,
  },
};
function selectionHtml(
  mode: "off" | "selective" | "full",
  status?: AIStatus,
  files = [selected],
) {
  return renderToStaticMarkup(
    <BatchSelection
      files={files}
      busy={false}
      reading={false}
      cancelling={false}
      scanMode={mode}
      ai={status}
      aiLoading={false}
      remove={() => {}}
      chooseMode={() => {}}
      refreshAI={() => {}}
      start={() => {}}
      cancel={() => {}}
    />,
  );
}
function startDisabled(html: string) {
  const start = html
    .match(/<button\b[\s\S]*?<\/button>/g)
    ?.find((button) => button.includes("Start scan"));
  assert.ok(start);
  return /\sdisabled(?:=|[ >])/.test(start);
}
assert.equal(uploadIssue(selected), null);
assert.equal(startDisabled(selectionHtml("off")), false);
assert.equal(startDisabled(selectionHtml("full")), true);
assert.equal(startDisabled(selectionHtml("full", ai)), false);
assert.match(selectionHtml("off"), /Remove format.pdf/);
assert.match(selectionHtml("off"), /Nothing is uploaded or scanned/);
assert.match(selectionHtml("full"), /Local LLM is not ready/);
const invalid = { ...selected, path: "notes.txt" };
assert.equal(startDisabled(selectionHtml("off", undefined, [invalid])), true);
assert.match(
  uploadIssue({ ...selected, path: "keys/format.pdf" }) ?? "",
  /Answer keys/,
);
assert.match(
  uploadIssue({ ...selected, file: { size: 25 * 1024 ** 2 + 1 } as File }) ??
    "",
  /Exceeds/,
);

function directory(children: unknown[]) {
  return {
    isFile: false,
    isDirectory: true,
    fullPath: "/format",
    createReader() {
      let sent = false;
      return {
        readEntries(callback: (entries: unknown[]) => void) {
          callback(sent ? [] : children);
          sent = true;
        },
      };
    },
  };
}
const fileEntry = {
  isFile: true,
  isDirectory: false,
  fullPath: "/format.pdf",
  file(callback: (file: File) => void) {
    callback(selected.file);
  },
};
const items = (count: number) =>
  [
    {
      webkitGetAsEntry: () =>
        directory([
          ...Array.from({ length: count }, () => fileEntry),
          directory([]),
        ]),
    },
  ] as unknown as DataTransferItemList;
assert.equal(
  (await droppedFiles(items(100), [] as unknown as FileList)).length,
  100,
);
await assert.rejects(
  droppedFiles(items(101), [] as unknown as FileList),
  /at most 100/,
);
console.log(
  "12 batch-selection validation/rendering assertions passed; metadata contracts only",
);

assert.doesNotMatch(selectionHtml("selective", ai), /seconds maximum|Ollama reviews|Rules and local semantic/);
assert.doesNotMatch(selectionHtml("full", ai), /Refresh local LLM status|all extracted readable text/);
assert.equal(startDisabled(selectionHtml("selective", ai)), false);
assert.match(selectionHtml("off"), /Python scanner/);
assert.match(selectionHtml("off"), /Scan mode/);
console.log("5 scan-mode rendering assertions passed");
