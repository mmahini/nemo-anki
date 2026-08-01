import { registerSW } from "virtual:pwa-register";

// How often an already-open tab re-checks for a new deployment. Installed
// PWAs (desktop/Android) are frequently left running for hours, and a
// service worker only checks for updates on its own when the page navigates
// — without this, those sessions would keep running stale code until the
// user happened to close and reopen the app.
const UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000;

/** Fired on window when a new version is downloaded and waiting. */
export const PWA_UPDATE_EVENT = "nemo:pwa-update";

let updateSW: ((reloadPage?: boolean) => Promise<void>) | null = null;
let updateReady = false;

/** Register the service worker and keep it fresh. `registerType: "prompt"`
 * (see vite.config.ts) parks a detected update in "waiting" until the user
 * accepts it — UpdateToast listens for PWA_UPDATE_EVENT and offers an
 * "update now" button that calls applyPwaUpdate(). */
export function initPwaUpdates(): void {
  if (!("serviceWorker" in navigator)) return;

  updateSW = registerSW({
    immediate: true,
    onNeedRefresh() {
      updateReady = true;
      window.dispatchEvent(new CustomEvent(PWA_UPDATE_EVENT));
    },
    onRegisteredSW(_url, registration) {
      if (!registration) return;
      window.setInterval(() => {
        registration.update().catch(() => {});
      }, UPDATE_CHECK_INTERVAL_MS);

      // Installed PWAs are often reopened from a home-screen/desktop icon
      // rather than freshly navigated to, so also check the moment the app
      // regains focus (e.g. switching back to it after a while).
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
          registration.update().catch(() => {});
        }
      });
    },
  });
}

/** An update is downloaded and waiting (for components that mount after the
 * event already fired). */
export function pwaUpdateReady(): boolean {
  return updateReady;
}

/** Activate the waiting service worker and reload onto the new version. */
export function applyPwaUpdate(): Promise<void> {
  return updateSW ? updateSW(true) : Promise.resolve();
}
