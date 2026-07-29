import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";

/** Thin status bar shown at the top of every in-app page: trial / active /
 * expired (with days left) or a "payment under review" note. */
export default function SubscriptionBanner() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const sub = user?.subscription;
  if (!sub) return null;

  const tone = sub.pending ? "pending" : sub.state;
  const message = sub.pending
    ? t("subscription.pendingBanner")
    : sub.state === "active"
      ? t("subscription.active", { days: sub.days_left })
      : sub.state === "trial"
        ? t("subscription.trial", { days: sub.days_left })
        : t("subscription.expired");

  return (
    <div className={`subbanner subbanner--${tone}`}>
      <span className="subbanner__msg">{message}</span>
      {!sub.pending && (
        <Link to="/app/subscribe" className="subbanner__cta">
          {sub.state === "active" ? t("subscription.renew") : t("subscription.subscribe")}
        </Link>
      )}
    </div>
  );
}
