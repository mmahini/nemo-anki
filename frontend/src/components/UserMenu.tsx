import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { updateMe } from "../auth/api";
import { applyLanguage } from "../i18n";

/** Top-right account menu: subscription, language and sign-out. Opens as a
 * dropdown on desktop and a bottom sheet on mobile (styled in styles.css). */
export default function UserMenu() {
  const { user, signOut, refreshUser } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

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

  const initial = (user?.email?.[0] ?? "?").toUpperCase();
  const sub = user?.subscription;
  const subTone = sub?.pending ? "pending" : sub?.state ?? "expired";
  const subLabel = sub?.pending
    ? t("subscription.pendingBanner")
    : sub?.state === "active"
      ? t("subscription.active", { days: sub.days_left })
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
              className="usermenu__item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              <span>{t("nav.subscription")}</span>
              <span className={`usermenu__badge usermenu__badge--${subTone}`}>{subLabel}</span>
            </Link>

            <button className="usermenu__item" role="menuitem" onClick={toggleLanguage}>
              <span>{t("nav.language")}</span>
              <span className="usermenu__value">{user?.ui_language === "fa" ? "فارسی" : "English"}</span>
            </button>

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
