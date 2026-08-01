import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { referralLink } from "../lib/referral";

/** Header "invite friends" button. Clicking copies the user's referral link
 * and opens a small popup confirming the copy, showing the link and — where
 * the platform supports it — a native share button. Whoever signs up through
 * the link gets a free month of Basic. */
export default function InviteButton() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // Clipboard access can be denied (permissions, old browsers); the popup
  // then presents the link itself to copy by hand instead of claiming success.
  const [copyOk, setCopyOk] = useState(false);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!user?.referral_code) return null;
  const link = referralLink(user.referral_code);
  const shareText = t("invite.shareText");

  async function invite() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(`${shareText}\n${link}`);
      ok = true;
    } catch {
      /* popup falls back to showing the link for manual copy */
    }
    setCopyOk(ok);
    setOpen(true);
  }

  async function share() {
    try {
      await navigator.share({ text: shareText, url: link });
      setOpen(false);
    } catch {
      /* cancelled — keep the popup with the copied link */
    }
  }

  return (
    <div className="invite">
      <button
        className="invitebtn"
        onClick={invite}
        title={t("invite.title")}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <svg viewBox="0 0 24 24" fill="none" aria-hidden width="16" height="16">
          <circle cx="9" cy="8" r="3.5" stroke="currentColor" strokeWidth="2" />
          <path d="M3.5 19c.8-3 3-4.5 5.5-4.5s4.7 1.5 5.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <path d="M18 6v6M15 9h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="invitebtn__label">{t("nav.invite")}</span>
      </button>

      {open && (
        <>
          <div className="invite__backdrop" onClick={() => setOpen(false)} />
          <div className="invite__panel" role="dialog" aria-label={t("invite.title")}>
            <p className="invite__done">
              {copyOk ? <>✅ {t("invite.copied")}</> : t("invite.linkTitle")}
            </p>
            <p className="invite__link" dir="ltr">{link}</p>
            <p className="invite__hint">{t("invite.popupHint")}</p>
            <div className="invite__actions">
              {"share" in navigator && (
                <button className="btn btn--primary" onClick={share}>
                  {t("invite.shareBtn")}
                </button>
              )}
              <button className="btn btn--ghost" onClick={() => setOpen(false)}>
                {t("invite.closeBtn")}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
