import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { RefreshCw } from "lucide-react";

export const HeaderActionsContext = createContext<HTMLElement | null>(null);

export function PageHeaderActions({ children }: { children: ReactNode }) {
  const host = useContext(HeaderActionsContext);
  return host ? createPortal(children, host) : null;
}

export function HeaderRefresh({
  label,
  busy,
  refresh,
}: {
  label: string;
  busy: boolean;
  refresh: () => void;
}) {
  return (
    <button
      type="button"
      className="header-icon-button"
      aria-label={label}
      title={label}
      disabled={busy}
      onClick={refresh}
    >
      <RefreshCw size={20} />
    </button>
  );
}
