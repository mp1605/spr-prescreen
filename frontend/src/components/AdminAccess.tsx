import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole, LogOut } from "lucide-react";
import { adminRequest, type Session } from "../api/admin";
import { AdminWorkspace } from "./AdminWorkspace";

export function AdminAccess() {
  const client = useQueryClient();
  const session = useQuery({
    queryKey: ["admin-session"],
    queryFn: () => adminRequest<Session>("/session"),
    refetchInterval: 60000,
  });
  useEffect(() => {
    if (session.data && !session.data.authenticated)
      client.removeQueries({
        predicate: (query) => String(query.queryKey[0]).startsWith("policy-"),
      });
  }, [client, session.data]);
  const [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function act(login: boolean) {
    setBusy(true);
    setError("");
    try {
      await adminRequest(
        login ? "/login" : "/logout",
        "POST",
        login ? { password } : undefined,
      );
      setPassword("");
      await session.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      id="rule-management"
      className="admin-access"
      aria-label="Rule management"
    >
      <div className="admin-section-heading">
        <div>
          <div className="eyebrow">AUTHORIZED EDITING</div>
          <h2>
            <LockKeyhole size={20} /> Rule management
          </h2>
          <p>
            Reviewers can read the lists. A local admin can update their
            screening indicators.
          </p>
        </div>
        {session.data?.authenticated && (
          <button
            className="outline-button"
            disabled={busy}
            onClick={() => void act(false)}
          >
            <LogOut size={15} /> Sign out
          </button>
        )}
      </div>
      {session.isPending ? (
        <p role="status">Checking local session…</p>
      ) : session.error ? (
        <p className="notice error" role="alert">
          Could not check admin access.{" "}
          <button onClick={() => void session.refetch()}>Retry</button>
        </p>
      ) : !session.data?.configured ? (
        <div className="notice">
          <strong>Initialize the admin locally</strong>
          <p>
            From the project directory, run{" "}
            <code>.venv/bin/python -m backend.admin init</code> in a terminal.
            The command prompts privately for a password. There is no default
            password or browser registration.
          </p>
          <button
            className="text-button"
            onClick={() => void session.refetch()}
          >
            Check setup again
          </button>
        </div>
      ) : !session.data.authenticated ? (
        <form
          className="admin-login"
          onSubmit={(event) => {
            event.preventDefault();
            void act(true);
          }}
        >
          <label>
            Admin password
            <input
              type="password"
              autoComplete="current-password"
              maxLength={1024}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button className="primary-button" disabled={busy || !password}>
            {busy ? "Signing in…" : "Sign in as admin"}
          </button>
          <small>
            Sessions expire after 30 minutes. Five sign-in attempts per minute.
          </small>
        </form>
      ) : (
        <>
          <p className="admin-session">
            Admin session · expires{" "}
            {new Date(session.data.expires_utc!).toLocaleTimeString()}
          </p>
          <AdminWorkspace />
        </>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <p className="source-note">
        Local prototype access control with a shared admin password; this is not
        production identity management.
      </p>
    </section>
  );
}
