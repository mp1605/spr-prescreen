// Official phrases and numeric render contracts only. No paper corpus or sponsor data.
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { ScorecardReport } from "../src/components/ScorecardReport";
import { rate, type EvaluationReport } from "../src/api/evaluation";
import { BatchSelection } from "../src/components/BatchSelection";
import {
  droppedFiles,
  uploadIssue,
  type SelectedUpload,
} from "../src/logic/uploads";
import type { AIStatus } from "../src/api/ai";

const report: EvaluationReport = {
  kind: "format_contract",
  paper_count: 1,
  trigger_count: 1,
  matched_triggers: 0,
  trigger_recall: 0,
  list1_recall: null,
  list2_recall: 0,
  item_accuracy: null,
  flag_color_accuracy: null,
  paper_color_accuracy: 0,
  confusion: {
    green: { green: 0, yellow: 0, red: 0 },
    yellow: { green: 1, yellow: 0, red: 0 },
    red: { green: 0, yellow: 0, red: 0 },
  },
  false_alarms: 0,
  greens_wrongly_flagged: 0,
  decoy_count: 0,
  decoys_flagged: 0,
  false_alarms_on_reference_papers: 0,
  incomplete_papers: 0,
  seconds_per_paper_ai_off: 0,
  seconds_per_paper_ai_on: null,
  rules_versions: ["numeric-contract"],
  matching_policy: "In-memory arithmetic and display only",
  cost_assumption: "Contract",
  weighted_cost: 3,
  cases: [
    {
      case_id: "display-contract",
      expected_color: "yellow",
      actual_color: "green",
      trigger_count: 1,
      matched_count: 0,
      missed: [
        {
          tag: "T1",
          quote: "Animal testing <script>literal text</script>",
          items: ["L2-01"],
          color: "yellow",
          reason: "Display escaping contract",
        },
      ],
      false_alarms: [],
      decoy_hits: [],
    },
  ],
};
const html = renderToStaticMarkup(<ScorecardReport report={report} />);
assert.equal(rate(0), "0.0%");
assert.equal(rate(null), "Not defined");
assert.match(html, /NOT SCANNER|do not measure scanner accuracy/i);
assert.match(html, /0\.00/); // A measured zero-second value must not become missing.
assert.match(html, /Not defined/);
assert.match(html, /Missed T1/);
assert.match(html, /1 expected triggers were not matched/);
assert.match(html, /&lt;script&gt;literal text&lt;\/script&gt;/);
assert.doesNotMatch(html, /<script>/);
assert.equal((html.match(/scope="row"/g) || []).length, 3);
assert.match(html, /Reference-paper false alarms/);
assert.match(html, /Not measured · no reference papers/);
console.log(
  "12 scorecard rendering assertions passed; format/numeric objects only, not scanner accuracy",
);

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

assert.match(selectionHtml("selective", ai), /not a full-paper LLM review/);
assert.match(selectionHtml("full", ai), /all extracted readable text/);
assert.equal(startDisabled(selectionHtml("selective", ai)), false);
assert.match(selectionHtml("off"), /Python scanner/);
assert.match(selectionHtml("off"), /Scan mode/);
console.log("5 scan-mode rendering assertions passed");
