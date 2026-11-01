import { useState } from "react";
import { adminRequest } from "../api/admin";
import type { AIStatus } from "../api/ai";

export function AISettingsForm({
  status,
  saved,
}: {
  status: AIStatus;
  saved: (value: AIStatus) => void;
}) {
  const [form, setForm] = useState(status.settings),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const hasModel = status.models.some((model) => model.name === form.model);
  const dirty = JSON.stringify(form) !== JSON.stringify(status.settings);
  async function save() {
    setBusy(true);
    setError("");
    try {
      saved(
        await adminRequest<AIStatus>("/ai", "PUT", {
          revision: status.revision,
          enabled: form.enabled,
          model: form.model,
          timeout_seconds: form.timeout_seconds,
          context_tokens: form.context_tokens,
          max_output_tokens: form.max_output_tokens,
        }),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "AI settings were not saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="ai-settings-form"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label className="ai-enable">
        <input
          type="checkbox"
          checked={form.enabled}
          disabled={busy || (!hasModel && !form.enabled)}
          onChange={(event) =>
            setForm({ ...form, enabled: event.target.checked })
          }
        />
        Default local AI for new batches
      </label>
      {!hasModel && (
        <p className="subtle">
          The selected model is not in the current local inventory. Configure a
          cached model and refresh before enabling. You can always switch AI
          off.
        </p>
      )}
      <div className="ai-settings-fields">
        <label>
          Local model tag
          <input
            value={form.model}
            maxLength={160}
            required
            list="local-ai-models"
            onChange={(event) =>
              setForm({ ...form, model: event.target.value })
            }
            disabled={busy}
          />
        </label>
        <datalist id="local-ai-models">
          {status.models.map((model) => (
            <option key={model.name} value={model.name} />
          ))}
        </datalist>
        <label>
          Total seconds per paper
          <input
            type="number"
            min={1}
            max={120}
            required
            value={form.timeout_seconds}
            onChange={(event) =>
              setForm({ ...form, timeout_seconds: Number(event.target.value) })
            }
            disabled={busy}
          />
        </label>
        <label>
          Context token budget
          <input
            type="number"
            min={2048}
            max={32768}
            required
            value={form.context_tokens}
            onChange={(event) =>
              setForm({ ...form, context_tokens: Number(event.target.value) })
            }
            disabled={busy}
          />
        </label>
        <label>
          Maximum output tokens
          <input
            type="number"
            min={256}
            max={4096}
            required
            value={form.max_output_tokens}
            onChange={(event) =>
              setForm({
                ...form,
                max_output_tokens: Number(event.target.value),
              })
            }
            disabled={busy}
          />
        </label>
      </div>
      <button className="outline-button" disabled={busy || !dirty}>
        {busy ? "Checking and saving…" : "Save AI settings"}
      </button>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <p className="subtle">
        Existing batches keep their recorded setting. Rescan creates a separate
        batch. Enabling checks and pins the local model digest; no model is
        downloaded or started.
      </p>
    </form>
  );
}
