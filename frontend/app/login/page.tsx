"use client";

import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(json?.error?.message || "Sign in failed.");
      }
      const params = new URLSearchParams(window.location.search);
      const next = params.get("next");
      // Same-site relative paths only: "//host" and "/\host" are protocol-relative
      // redirects to attacker domains, so a bare startsWith("/") check is not enough.
      window.location.href = next && /^\/(?![/\\])/.test(next) ? next : "/paper-trading";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[68vh] max-w-md items-center">
      <form onSubmit={submit} className="w-full rounded-2xl border border-line bg-surface/80 p-6 shadow-2xl shadow-black/20">
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-wider text-muted">Atlas account</div>
          <h1 className="mt-2 font-serif text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-2 text-sm text-muted">Required for your private Paper Trading, Watchlists, and Screener workspaces.</p>
        </div>

        <label className="mb-4 block">
          <span className="mb-1.5 block text-xs text-muted">Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-lg border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-accent"
            autoComplete="username"
          />
        </label>

        <label className="mb-5 block">
          <span className="mb-1.5 block text-xs text-muted">Password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-accent"
            type="password"
            autoComplete="current-password"
            autoFocus
          />
        </label>

        {error && <div className="mb-4 rounded-lg border border-negative/30 bg-negative/10 px-3 py-2 text-sm text-negative">{error}</div>}

        <button disabled={busy} className="w-full rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white shadow-glow disabled:opacity-60">
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
