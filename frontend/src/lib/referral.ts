/**
 * Referral link plumbing. An invite link is any app URL with `?ref=<code>`
 * (shared as the site root, e.g. https://anki.nemoapps.xyz/?ref=abc123).
 * The code is stashed in localStorage on first page load so it survives the
 * sign-in / OTP round-trip, then sent with verify-otp and cleared.
 */

const REF_KEY = "nemo-anki.ref";
/** Set after verify-otp granted the reward; the welcome flow shows the gift
 * banner and this dies with the tab. */
const GIFT_KEY = "nemo-anki.referral-gift";

/** Pick `?ref=` out of the current URL and remember it. Call once on boot. */
export function captureReferralCode() {
  try {
    const code = new URLSearchParams(window.location.search).get("ref")?.trim();
    if (code) localStorage.setItem(REF_KEY, code);
  } catch {
    /* storage unavailable — the invite just degrades to a plain link */
  }
}

export function storedReferralCode(): string | null {
  try {
    return localStorage.getItem(REF_KEY);
  } catch {
    return null;
  }
}

export function clearReferralCode() {
  try {
    localStorage.removeItem(REF_KEY);
  } catch {
    /* ignore */
  }
}

export function markReferralGift() {
  try {
    sessionStorage.setItem(GIFT_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function hasReferralGift(): boolean {
  try {
    return sessionStorage.getItem(GIFT_KEY) === "1";
  } catch {
    return false;
  }
}

/** The invite link the current user shares. */
export function referralLink(code: string): string {
  return `${window.location.origin}/?ref=${code}`;
}
