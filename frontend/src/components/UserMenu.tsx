import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { telegramConnect, telegramStatus, updateMe } from "../auth/api";
import { applyLanguage } from "../i18n";
import { subscribeToPush } from "../lib/pushNotifications";
import { disableSupportPush, enableSupportPush, isSubscribedToPush, pushSupported } from "../push";
import { useSubscription } from "../subscription/SubscriptionContext";

const TELEGRAM_POLL_INTERVAL_MS = 2000;
const TELEGRAM_POLL_MAX_ATTEMPTS = 60; // ~2 minutes

/** Top-right account menu: subscription, language and sign-out. Opens as a
 * dropdown on desktop and a bottom sheet on mobile (styled in styles.css). */
export default function UserMenu() {
  const { user, signOut, refreshUser } = useAuth();
  const { sub } = useSubscription();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [pushOn, setPushOn] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [reminderError, setReminderError] = useState<string | null>(null);
  const [connectingTelegram, setConnectingTelegram] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (!user?.is_staff || !pushSupported()) return;
    isSubscribedToPush().then(setPushOn).catch(() => {});
  }, [user?.is_staff]);

  async function toggleSupportPush() {
    if (pushBusy) return;
    setPushBusy(true);
    try {
      if (pushOn) {
        await disableSupportPush();
        setPushOn(false);
      } else {
        await enableSupportPush();
        setPushOn(true);
      }
    } catch (e) {
      window.alert(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setPushBusy(false);
    }
  }

  async function toggleLanguage() {
    const next = user?.ui_language === "fa" ? "en" : "fa";
    applyLanguage(next);
    try {
      await updateMe({ ui_language: next });
    } catch {
      applyLanguage(user?.ui_language ?? "en");
      return;
    }
    refreshUser().catch(() => {});
  }

  async function handleReminderChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value; // "" (cleared) or "HH:MM"
    setReminderError(null);
    if (!value) {
      try {
        await updateMe({ study_reminder_time: null });
        refreshUser().catch(() => {});
      } catch {
        setReminderError(t("studyReminder.saveFailed"));
      }
      return;
    }
    if ((user?.study_reminder_channel ?? "push") === "push") {
      try {
        await subscribeToPush();
      } catch (err) {
        setReminderError(
          err instanceof Error && err.message === "permission-denied"
            ? t("studyReminder.permissionDenied")
            : t("studyReminder.unsupported"),
        );
        return;
      }
    }
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    try {
      await updateMe({ study_reminder_time: `${value}:00`, study_reminder_timezone: tz });
      refreshUser().catch(() => {});
    } catch {
      setReminderError(t("studyReminder.saveFailed"));
    }
  }

  async function handleReminderChannelChange(channel: "push" | "telegram") {
    setReminderError(null);
    try {
      await updateMe({ study_reminder_channel: channel });
      await refreshUser();
    } catch {
      setReminderError(t("studyReminder.saveFailed"));
      return;
    }
    if (channel === "telegram" && !user?.telegram_connected) {
      startTelegramConnect();
    }
  }

  async function startTelegramConnect() {
    setReminderError(null);
    setConnectingTelegram(true);
    let deepLink: string;
    try {
      ({ deep_link: deepLink } = await telegramConnect());
    } catch {
      setConnectingTelegram(false);
      setReminderError(t("studyReminder.telegramUnavailable"));
      return;
    }
    window.open(deepLink, "_blank");

    let attempts = 0;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      attempts += 1;
      try {
        const { connected } = await telegramStatus();
        if (connected) {
          if (pollRef.current) clearInterval(pollRef.current);
          setConnectingTelegram(false);
          refreshUser().catch(() => {});
          return;
        }
      } catch {
        // Transient — keep polling until attempts run out.
      }
      if (attempts >= TELEGRAM_POLL_MAX_ATTEMPTS) {
        if (pollRef.current) clearInterval(pollRef.current);
        setConnectingTelegram(false);
      }
    }, TELEGRAM_POLL_INTERVAL_MS);
  }

  // Prefer the name they gave during onboarding; fall back to the email.
  const initial = (user?.display_name?.trim()?.[0] || user?.email?.[0] || "?").toUpperCase();
  const subTone = sub?.pending ? "pending" : sub?.state ?? "expired";
  const tierLabel = sub?.tier === "pro" ? t("subscription.tierPro") : t("subscription.tierBasic");
  const subLabel = sub?.pending
    ? t("subscription.pendingBanner")
    : sub?.state === "active"
      ? t("subscription.activeTier", { tier: tierLabel, days: sub.days_left })
      : sub?.state === "trial"
        ? t("subscription.trial", { days: sub.days_left })
        : t("subscription.expired");

  return (
    <div className="usermenu" ref={ref}>
      <button
        className="usermenu__btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user?.email}
      >
        <span className="usermenu__avatar">{initial}</span>
      </button>

      {open && (
        <>
          <div className="usermenu__backdrop" onClick={() => setOpen(false)} />
          <div className="usermenu__panel" role="menu">
            <div className="usermenu__head">
              <span className="usermenu__avatar usermenu__avatar--lg">{initial}</span>
              <span className="usermenu__email">{user?.email}</span>
            </div>

            <Link
              to="/app/subscribe"
              className="usermenu__item usermenu__item--stacked"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              <span className="usermenu__itemlabel">{t("nav.subscription")}</span>
              <span className={`usermenu__badge usermenu__badge--${subTone}`}>{subLabel}</span>
            </Link>

            <Link
              to="/app/stats"
              className="usermenu__item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              {t("nav.stats")}
            </Link>

            <Link
              to="/welcome"
              className="usermenu__item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              {t("nav.howItWorks")}
            </Link>

            <Link
              to="/app/support"
              className="usermenu__item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              {t("nav.support")}
            </Link>

            {user?.is_staff && pushSupported() && (
              <button
                className="usermenu__item"
                role="menuitem"
                onClick={toggleSupportPush}
                disabled={pushBusy}
              >
                <span>{t("nav.supportAlerts")}</span>
                <span className="usermenu__value">
                  {pushOn ? t("nav.supportAlertsOn") : t("nav.supportAlertsOff")}
                </span>
              </button>
            )}

            <button className="usermenu__item" role="menuitem" onClick={toggleLanguage}>
              <span>{t("nav.language")}</span>
              <span className="usermenu__value">{user?.ui_language === "fa" ? "فارسی" : "English"}</span>
            </button>

            <div className="usermenu__item usermenu__item--stacked" role="menuitem">
              <span className="usermenu__itemlabel">{t("studyReminder.label")}</span>
              <div className="usermenu__reminderchannels">
                <button
                  type="button"
                  className={`usermenu__chip${
                    (user?.study_reminder_channel ?? "push") === "push" ? " usermenu__chip--active" : ""
                  }`}
                  onClick={() => handleReminderChannelChange("push")}
                >
                  {t("studyReminder.channelPush")}
                </button>
                <button
                  type="button"
                  className={`usermenu__chip${
                    user?.study_reminder_channel === "telegram" ? " usermenu__chip--active" : ""
                  }`}
                  onClick={() => handleReminderChannelChange("telegram")}
                >
                  {t("studyReminder.channelTelegram")}
                </button>
              </div>

              {user?.study_reminder_channel === "telegram" && !user?.telegram_connected ? (
                <button
                  type="button"
                  className="input input--sm"
                  onClick={startTelegramConnect}
                  disabled={connectingTelegram}
                >
                  {connectingTelegram ? t("studyReminder.waitingForTelegram") : t("studyReminder.connectTelegram")}
                </button>
              ) : (
                <input
                  type="time"
                  className="input input--sm"
                  value={user?.study_reminder_time?.slice(0, 5) ?? ""}
                  onChange={handleReminderChange}
                />
              )}

              <span className="usermenu__value">
                {reminderError ??
                  (user?.study_reminder_channel === "telegram" && user?.telegram_connected
                    ? t("studyReminder.telegramConnected")
                    : t("studyReminder.hint"))}
              </span>
            </div>

            <button
              className="usermenu__item usermenu__item--danger"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                signOut();
                navigate("/");
              }}
            >
              {t("nav.signOut")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
