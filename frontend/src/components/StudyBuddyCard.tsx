import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { acceptBuddy, fetchBuddy, inviteBuddy, nudgeBuddy, removeBuddy, type BuddyState } from "../auth/api";

/** Home card for the study-buddy pairing: invite by email, accept/decline,
 * or (once paired) see both people's today/streak side by side + nudge. */
export default function StudyBuddyCard() {
  const { t } = useTranslation();
  const [state, setState] = useState<BuddyState | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBuddy()
      .then(setState)
      .catch(() => {});
  }, []);

  async function onInvite() {
    if (!email.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setState(await inviteBuddy(email.trim()));
      setEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onAccept() {
    setBusy(true);
    try {
      setState(await acceptBuddy());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onRemove() {
    setBusy(true);
    try {
      await removeBuddy();
      setState({ status: "none" });
    } finally {
      setBusy(false);
    }
  }

  async function onNudge() {
    setBusy(true);
    try {
      await nudgeBuddy();
      setState((s) => (s && s.status === "accepted" ? { ...s, nudged_today: true } : s));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  if (!state) return null;

  return (
    <section className="buddycard">
      <h2 className="buddycard__title">{t("studyBuddy.title")}</h2>

      {state.status === "none" && (
        <>
          <p className="buddycard__hint">{t("studyBuddy.hint")}</p>
          <div className="buddycard__row">
            <input
              className="input"
              type="email"
              placeholder={t("studyBuddy.emailPlaceholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onInvite()}
            />
            <button className="btn btn--primary btn--sm" disabled={!email.trim() || busy} onClick={onInvite}>
              {busy ? t("studyBuddy.inviting") : t("studyBuddy.inviteBtn")}
            </button>
          </div>
          {error && <p className="auth__error">{error}</p>}
        </>
      )}

      {state.status === "pending_sent" && (
        <div className="buddycard__row">
          <p className="buddycard__hint">{t("studyBuddy.waitingFor", { email: state.email })}</p>
          <button className="btn btn--ghost btn--sm" disabled={busy} onClick={onRemove}>
            {t("studyBuddy.cancelBtn")}
          </button>
        </div>
      )}

      {state.status === "pending_received" && (
        <div className="buddycard__row">
          <p className="buddycard__hint">{t("studyBuddy.invitedYou", { email: state.email })}</p>
          <button className="btn btn--primary btn--sm" disabled={busy} onClick={onAccept}>
            {t("studyBuddy.acceptBtn")}
          </button>
          <button className="btn btn--ghost btn--sm" disabled={busy} onClick={onRemove}>
            {t("studyBuddy.declineBtn")}
          </button>
        </div>
      )}

      {state.status === "accepted" && (
        <>
          <div className="buddycard__stats">
            <div className="buddycard__stat">
              <span className="buddycard__statlabel">{t("studyBuddy.you")}</span>
              <span className="buddycard__statvalue">{t("studyBuddy.todayCount", { count: state.me.today })}</span>
              {state.me.streak > 0 && <span className="buddycard__streak">🔥 {state.me.streak}</span>}
            </div>
            <div className="buddycard__stat">
              <span className="buddycard__statlabel">{state.buddy_email}</span>
              <span className="buddycard__statvalue">
                {t("studyBuddy.todayCount", { count: state.buddy.today })}
              </span>
              {state.buddy.streak > 0 && <span className="buddycard__streak">🔥 {state.buddy.streak}</span>}
            </div>
          </div>
          <div className="buddycard__row">
            <button className="btn btn--ghost btn--sm" disabled={busy || state.nudged_today} onClick={onNudge}>
              {state.nudged_today ? t("studyBuddy.nudgedBtn") : t("studyBuddy.nudgeBtn")}
            </button>
            <button className="btn btn--ghost btn--sm" disabled={busy} onClick={onRemove}>
              {t("studyBuddy.unpairBtn")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
