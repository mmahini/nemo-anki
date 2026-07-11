import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { verifyOtp } from "../auth/api";
import { useAuth } from "../auth/AuthContext";

type VerifyLocationState = {
  otpId?: string;
  devCode?: string;
  email?: string;
};

export default function Verify() {
  const location = useLocation();
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const { t } = useTranslation();
  const state = (location.state as VerifyLocationState | null) ?? {};

  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!state.otpId) {
    return <Navigate to="/auth/sign-in" replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!state.otpId) return;
    setError(null);
    setSubmitting(true);
    try {
      const r = await verifyOtp(state.otpId, code.trim());
      signIn(
        { access: r.access, refresh: r.refresh, user: r.user },
        { isNewUser: r.is_new_user },
      );
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth">
      <div className="auth__card">
        <h1>{t("verify.title")}</h1>
        <p className="auth__sub">
          {state.devCode
            ? `We generated a 5-digit code${state.email ? ` for ${state.email}` : ""}.`
            : `We've emailed a 5-digit code${state.email ? ` to ${state.email}` : ""}. Check your inbox (and spam) and enter it below.`}
        </p>

        {state.devCode && (
          <div className="dev-banner" role="status">
            <span className="dev-banner__label">DEV — your code is</span>
            <span className="dev-banner__code">{state.devCode}</span>
            <span className="dev-banner__note">
              No email key configured here, so we&apos;re showing it for local testing.
            </span>
          </div>
        )}

        <form onSubmit={onSubmit} className="auth__form">
          <label className="auth__label">
            {t("verify.codeLabel")}
            <input
              type="text"
              inputMode="numeric"
              pattern="\d{5}"
              required
              autoFocus
              maxLength={5}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="12345"
              className="auth__input auth__input--code"
              disabled={submitting}
            />
          </label>
          {error && <p className="auth__error">{error}</p>}
          <button
            className="btn btn--primary"
            type="submit"
            disabled={submitting || code.length !== 5}
          >
            {submitting ? t("verify.verifying") : t("verify.verifyBtn")}
          </button>
        </form>
        <button
          type="button"
          className="auth__link"
          onClick={() => navigate("/auth/sign-in")}
        >
          {t("verify.backBtn")}
        </button>
      </div>
    </main>
  );
}
