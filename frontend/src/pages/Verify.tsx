import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { verifyOtp } from "../auth/api";
import { useAuth } from "../auth/AuthContext";
import { clearReferralCode, markReferralGift, storedReferralCode } from "../lib/referral";

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
      const r = await verifyOtp(state.otpId, code.trim(), storedReferralCode());
      // One shot either way: applied (reward granted) or ignored (existing
      // account / bad code) — don't let a stale code tag along forever.
      clearReferralCode();
      if (r.referral_applied) markReferralGift();
      signIn(
        { access: r.access, refresh: r.refresh, user: r.user },
        { isNewUser: r.is_new_user },
      );
      // Straight into the walkthrough for a brand-new account, so there's no
      // flash of the deck list before ProtectedRoute bounces them there.
      navigate(r.user.onboarded ? "/app" : "/welcome", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("verify.failed"));
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
            ? state.email
              ? t("verify.subDev", { email: state.email })
              : t("verify.subDevNoEmail")
            : state.email
              ? t("verify.sub", { email: state.email })
              : t("verify.subNoEmail")}
        </p>

        {state.devCode && (
          <div className="dev-banner" role="status">
            <span className="dev-banner__label">{t("verify.devLabel")}</span>
            <span className="dev-banner__code">{state.devCode}</span>
            <span className="dev-banner__note">{t("verify.devNote")}</span>
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
