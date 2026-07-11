import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { requestOtp } from "../auth/api";

export default function SignIn() {
  const navigate = useNavigate();
  const { t } = useTranslation();
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
        <h1>{t("signIn.title")}</h1>
        <form onSubmit={onSubmit} className="auth__form">
          <label className="auth__label">
            {t("signIn.emailLabel")}
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("signIn.emailPlaceholder")}
              className="auth__input"
              disabled={submitting}
            />
          </label>
          {error && <p className="auth__error">{error}</p>}
          <button className="btn btn--primary" type="submit" disabled={submitting}>
            {submitting ? t("signIn.sending") : t("signIn.continueBtn")}
          </button>
        </form>
        <p className="auth__hint">
          {t("signIn.hint")}
        </p>
      </div>
    </main>
  );
}
