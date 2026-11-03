import { useState } from "react";
import { login, logout, register } from "../../../shared/auth/api.js";

// DRF sends form errors as {field: ["message"]}, which ApiError's message doesn't include.
function errorText(err) {
  const firstFieldError = Object.values(err.body ?? {}).flat()[0];
  return err.body?.detail || firstFieldError || err.message;
}

export default function AuthBar({ user, onChange }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      setPassword("");
      onChange(result?.user ?? null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (user) {
    return (
      <div className="d-flex align-items-center gap-2">
        <span className="text-secondary">Signed in as {user.username}</span>
        <button type="button" className="btn btn-sm btn-outline-primary" disabled={busy} onClick={() => run(logout)}>
          Log out
        </button>
        {error && <span className="text-sp-red small" role="alert">{error}</span>}
      </div>
    );
  }

  return (
    <form
      className="d-flex flex-wrap align-items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        run(() => login(username, password));
      }}
    >
      <span className="text-secondary small">Sign in to vote</span>
      <input
        className="form-control form-control-sm w-auto"
        aria-label="Username"
        placeholder="Username"
        autoComplete="username"
        required
        value={username}
        onChange={(event) => setUsername(event.target.value)}
      />
      <input
        className="form-control form-control-sm w-auto"
        aria-label="Password"
        placeholder="Password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button type="submit" className="btn btn-sm btn-primary" disabled={busy}>
        Log in
      </button>
      <button
        type="button"
        className="btn btn-sm btn-outline-primary"
        disabled={busy || !username || !password}
        onClick={() => run(() => register(username, password))}
      >
        Register
      </button>
      {error && <span className="text-sp-red small w-100" role="alert">{error}</span>}
    </form>
  );
}
