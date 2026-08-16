import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { cdpTrack } from "../lib/cdp-pixel";

/** "Add to Home Screen" nudge for mobile-browser visitors.
 *
 * Installed usage is stickier (full screen, home-screen icon, survives tab
 * hygiene), and much of the audience doesn't know a PWA can be installed at
 * all — so we tell them, once, politely:
 *  - Android Chrome-family: the real install prompt via `beforeinstallprompt`.
 *  - iOS (no install API): illustrated share → Add to Home Screen steps.
 *  - Other mobile browsers: menu → Add to Home screen steps.
 *
 * Never shown when already running installed (display-mode), on desktop, or
 * within the snooze window after a dismissal. `appinstalled` (or a completed
 * native prompt) retires it permanently.
 */

const STORAGE_KEY = "nemo-anki.a2hs";
const SNOOZE_DAYS = 14;

type Stored = { done?: boolean; dismissedAt?: number };

function readStored(): Stored {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") as Stored;
  } catch {
    return {};
  }
}

function writeStored(patch: Stored): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readStored(), ...patch }));
  } catch {
    // storage blocked — we'll just ask again next visit
  }
}

function isInstalled(): boolean {
  try {
    return (
      (navigator as { standalone?: boolean }).standalone === true ||
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches ||
      window.matchMedia("(display-mode: minimal-ui)").matches
    );
  } catch {
    return false;
  }
}

function platform(): "ios" | "android" | "other" {
  const ua = navigator.userAgent;
  // iPadOS 13+ masquerades as macOS; the touch check unmasks it.
  if (/iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1)) {
    return "ios";
  }
  if (/android/i.test(ua)) return "android";
  return "other";
}

// `beforeinstallprompt` fires early, often before React mounts — capture it at
// module scope so the button can replay it whenever the sheet appears.
type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};
let deferredPrompt: BeforeInstallPromptEvent | null = null;
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // we choose the moment, not the browser
    deferredPrompt = e as BeforeInstallPromptEvent;
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    writeStored({ done: true });
  });
}

/* The two glyphs the iOS steps talk about — drawn inline so the instruction
   and the button the user must find look the same. */
function IconShare() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3v11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8.5 6.5L12 3l3.5 3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 10H6a2 2 0 00-2 2v7a2 2 0 002 2h12a2 2 0 002-2v-7a2 2 0 00-2-2h-1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconAddBox() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="4" y="4" width="16" height="16" rx="4" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 8.5v7M8.5 12h7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconMenuDots() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="12" cy="5" r="1.7" />
      <circle cx="12" cy="12" r="1.7" />
      <circle cx="12" cy="19" r="1.7" />
    </svg>
  );
}

export default function InstallPrompt() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const os = platform();

  useEffect(() => {
    if (os === "other" || isInstalled()) return;
    const stored = readStored();
    if (stored.done) return;
    if (stored.dismissedAt && Date.now() - stored.dismissedAt < SNOOZE_DAYS * 24 * 3600 * 1000) {
      return;
    }
    // Let the page land first; a popup racing the first paint feels hostile.
    const id = window.setTimeout(() => {
      setOpen(true);
      cdpTrack("pwa_install_prompt", { action: "shown", os });
    }, 2500);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!open) return null;

  function dismiss() {
    writeStored({ dismissedAt: Date.now() });
    cdpTrack("pwa_install_prompt", { action: "dismissed", os });
    setOpen(false);
  }

  async function installNative() {
    const evt = deferredPrompt;
    if (!evt) {
      // No captured prompt (Firefox, Samsung Internet, already used) — teach
      // the manual route instead.
      setShowSteps(true);
      return;
    }
    deferredPrompt = null;
    await evt.prompt();
    const choice = await evt.userChoice.catch(() => ({ outcome: "dismissed" as const }));
    if (choice.outcome === "accepted") {
      writeStored({ done: true });
      cdpTrack("pwa_install_prompt", { action: "accepted", os });
      setOpen(false);
    } else {
      dismiss();
    }
  }

  function acknowledgeSteps() {
    // "Got it" — they've seen the steps; treat as done so we don't nag
    // someone who followed them (appinstalled never fires on iOS).
    writeStored({ done: true });
    cdpTrack("pwa_install_prompt", { action: "steps_acknowledged", os });
    setOpen(false);
  }

  const steps =
    os === "ios"
      ? [
          { icon: <IconShare />, text: t("install.iosStep1") },
          { icon: <IconAddBox />, text: t("install.iosStep2") },
          { icon: null, text: t("install.iosStep3") },
        ]
      : [
          { icon: <IconMenuDots />, text: t("install.androidStep1") },
          { icon: <IconAddBox />, text: t("install.androidStep2") },
        ];
  const stepsVisible = os === "ios" || showSteps;

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={t("install.title")}>
      <button className="sheet__backdrop" aria-label={t("common.close")} onClick={dismiss} />
      <div className="sheet__panel install">
        <div className="sheet__handle" aria-hidden />

        <img className="install__appicon" src="/pwa-192x192.png" alt="" aria-hidden />
        <h2 className="install__title">{t("install.title")}</h2>
        <p className="install__lede">{t("install.lede")}</p>

        {stepsVisible && (
          <ol className="install__steps">
            {steps.map((s, i) => (
              <li key={i} className="install__step">
                <span className="install__stepnum" aria-hidden>
                  {i + 1}
                </span>
                <span className="install__steptext">
                  {s.text}
                  {s.icon && <span className="install__glyph">{s.icon}</span>}
                </span>
              </li>
            ))}
          </ol>
        )}

        <div className="install__actions">
          {os === "android" && !showSteps ? (
            <button className="btn btn--primary install__cta" onClick={() => void installNative()}>
              {t("install.installBtn")}
            </button>
          ) : (
            <button className="btn btn--primary install__cta" onClick={acknowledgeSteps}>
              {t("install.gotIt")}
            </button>
          )}
          <button className="install__later" onClick={dismiss}>
            {t("install.later")}
          </button>
        </div>
      </div>
    </div>
  );
}
