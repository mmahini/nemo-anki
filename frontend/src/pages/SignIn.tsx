import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { requestOtp } from "../auth/api";

export default function SignIn() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const r = await requestOtp(email.trim().toLowerCase());
      navigate("/auth/verify", {
        state: { otpId: r.otp_id, devCode: r.dev_code, email },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth">
      <div className="auth__card">
        <Link to="/" className="auth__brand">← Nemo Anki</Link>
        <h1>Sign in</h1>
        <p className="auth__sub">Enter your email and we'll generate a 5-digit code.</p>
        <form onSubmit={onSubmit} className="auth__form">
          <label className="auth__label">
            Email
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="auth__input"
              disabled={submitting}
            />
          </label>
          {error && <p className="auth__error">{error}</p>}
          <button className="btn btn--primary" type="submit" disabled={submitting}>
            {submitting ? "Sending…" : "Send code"}
          </button>
        </form>
        <p className="auth__hint">
          New here? Same form — we'll create your account when you verify.
        </p>
      </div>
    </main>
  );
}
