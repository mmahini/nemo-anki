import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { referralLink } from "../lib/referral";

/** Header "invite friends" button: shares (or copies) the user's referral
 * link. Whoever signs up through it gets a free month of Basic. */
export default function InviteButton() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const timer = useRef<number>();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  if (!user?.referral_code) return null;
  const link = referralLink(user.referral_code);

  async function invite() {
    // Native share where it exists (mobile); clipboard everywhere else.
    if (navigator.share) {
      try {
        await navigator.share({ text: t("invite.shareText"), url: link });
        return;
      } catch (err) {
        // Cancelled is fine; anything else falls through to the clipboard.
        if (err instanceof DOMException && err.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(`${t("invite.shareText")}\n${link}`);
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt(t("invite.copyManually"), link);
    }
  }

  return (
    <button className="invitebtn" onClick={invite} title={t("invite.title")}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden width="16" height="16">
        <circle cx="9" cy="8" r="3.5" stroke="currentColor" strokeWidth="2" />
        <path d="M3.5 19c.8-3 3-4.5 5.5-4.5s4.7 1.5 5.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M18 6v6M15 9h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span className="invitebtn__label">
        {copied ? t("invite.copied") : t("nav.invite")}
      </span>
    </button>
  );
}
