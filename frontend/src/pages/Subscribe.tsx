import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { fetchSubscriptionPlans, submitSubscriptionClaim, type SubscriptionPlans } from "../auth/api";

export default function Subscribe() {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();
  const sub = user?.subscription;

  const [data, setData] = useState<SubscriptionPlans | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [txRef, setTxRef] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSubscriptionPlans().then(setData).catch(() => {});
  }, []);

  const address = data?.payment.address ?? "";
  const network = data?.payment.network ?? "";
  const selectedPlan = data?.plans.find((p) => p.key === selected) ?? null;

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — the address is visible to copy manually */
    }
  }

  async function onPaid() {
    if (!selected) {
      setError(t("subscription.selectPlanFirst"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await submitSubscriptionClaim(selected, txRef.trim());
      setSubmitted(true);
      refreshUser().catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setSubmitting(false);
    }
  }

  const statusMsg = sub?.pending
    ? t("subscription.statusPending")
    : sub?.state === "active"
      ? t("subscription.statusActive", { days: sub.days_left })
      : sub?.state === "trial"
        ? t("subscription.statusTrial", { days: sub.days_left })
        : t("subscription.statusExpired");
  const statusTone = sub?.pending ? "pending" : sub?.state ?? "expired";
  const done = submitted || sub?.pending;

  return (
    <div className="subscribe">
      <h1>{t("subscription.pageTitle")}</h1>
      <p className="subscribe__sub">{t("subscription.pageSubtitle")}</p>

      <div className={`subscribe__status subscribe__status--${statusTone}`}>{statusMsg}</div>

      {done ? (
        <div className="panel subscribe__thanks">{t("subscription.paidThanks")}</div>
      ) : (
        <>
          <h2 className="subscribe__h2">{t("subscription.choosePlan")}</h2>
          <div className="subscribe__plans">
            {data?.plans.map((p) => (
              <button
                key={p.key}
                type="button"
                className={`plancard ${selected === p.key ? "plancard--on" : ""}`}
                onClick={() => setSelected(p.key)}
              >
                <span className="plancard__price">${p.price_usd}</span>
                <span className="plancard__label">{p.label}</span>
              </button>
            ))}
          </div>

          <div className="panel subscribe__pay">
            <h2 className="subscribe__h2">{t("subscription.payTitle")}</h2>
            <p className="subscribe__payintro">{t("subscription.payIntro", { network })}</p>
            <div className="subscribe__payrow">
              <span>{t("subscription.network")}</span>
              <strong>{network || "—"}</strong>
            </div>
            <div className="subscribe__payrow">
              <span>{t("subscription.amount")}</span>
              <strong>{selectedPlan ? `$${selectedPlan.price_usd}` : "—"}</strong>
            </div>
            <div className="subscribe__wallet">
              <span className="subscribe__walletlabel">{t("subscription.wallet")}</span>
              <div className="subscribe__walletrow">
                <code className="subscribe__addr">{address || "…"}</code>
                <button type="button" className="btn btn--ghost btn--sm" onClick={copyAddress}>
                  {copied ? t("subscription.copied") : t("subscription.copy")}
                </button>
              </div>
            </div>

            <label className="subscribe__tx">
              <span className="subscribe__walletlabel">{t("subscription.txLabel")}</span>
              <input
                className="input"
                value={txRef}
                onChange={(e) => setTxRef(e.target.value)}
                placeholder={t("subscription.txPlaceholder")}
              />
              <span className="subscribe__txhint">{t("subscription.txHint")}</span>
            </label>

            {error && <p className="auth__error">{error}</p>}
            <button className="btn btn--primary btn--lg" onClick={onPaid} disabled={submitting}>
              {submitting ? t("subscription.submitting") : t("subscription.transferredBtn")}
            </button>
          </div>
        </>
      )}

      <Link to="/app" className="subscribe__back">{t("subscription.backToApp")}</Link>
    </div>
  );
}
