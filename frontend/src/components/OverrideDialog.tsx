import { forwardRef, useState } from "react";
export const OverrideDialog = forwardRef<
  HTMLDialogElement,
  { save: (reason: string) => void }
>(function OverrideDialog({ save }, ref) {
  const [reason, setReason] = useState("");
  return (
    <dialog
      ref={ref}
      className="override-dialog"
      aria-labelledby="override-title"
    >
      <form
        method="dialog"
        onSubmit={(event) => {
          const submitter = (event.nativeEvent as SubmitEvent).submitter;
          if (submitter?.getAttribute("value") === "save") {
            save(reason);
            setReason("");
          }
        }}
      >
        <div className="eyebrow">HUMAN REVIEW</div>
        <h2 id="override-title">Override this flag</h2>
        <p>The raw finding and screening color will stay in the record.</p>
        <label>
          Reason preset
          <select value="" onChange={(event) => setReason(event.target.value)}>
            <option value="">Choose a reason (optional)</option>
            {[
              "Publicly available information",
              "Context does not support this item",
              "Pattern matched unrelated wording",
              "Requires separate manual review",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Reason (optional)
          <textarea
            maxLength={2000}
            rows={4}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <div className="flag-actions">
          <button className="outline-button" value="cancel">
            Cancel
          </button>
          <button className="primary-button" value="save">
            Save override
          </button>
        </div>
      </form>
    </dialog>
  );
});
