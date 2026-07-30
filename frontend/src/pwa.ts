import { registerSW } from "virtual:pwa-register";

// How often an already-open tab re-checks for a new deployment. Installed
// PWAs (desktop/Android) are frequently left running for hours, and a
// service worker only checks for updates on its own when the page navigates
// — without this, those sessions would keep running stale code until the
// user happened to close and reopen the app.
const UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000;

/** Register the service worker and keep it fresh. `registerType: "autoUpdate"`
 * (see vite.config.ts) makes a detected update apply and reload immediately —
 * no "reload to update" prompt — so once this fires, users on an installed
 * PWA see the latest version without ever uninstalling/reinstalling. */
export function initPwaUpdates(): void {
  if (!("serviceWorker" in navigator)) return;

  const updateSW = registerSW({
    immediate: true,
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

  void updateSW;
}
