import { subscribeToSupportPush, unsubscribeFromSupportPush } from "./auth/api";

// Baked in at build time (see vite.config.ts / VITE_VAPID_PUBLIC_KEY) — the
// public key isn't secret, it just identifies this app to the push service.
const VAPID_PUBLIC_KEY = ((import.meta as any).env.VITE_VAPID_PUBLIC_KEY ?? "") as string;

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    !!VAPID_PUBLIC_KEY
  );
}

/** Whether this browser already holds an active push subscription — used to
 * show "on"/"off" state for the opt-in toggle. */
export async function isSubscribedToPush(): Promise<boolean> {
  if (!pushSupported()) return false;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  return !!sub;
}

/** Ask for notification permission (if needed) and register this browser
 * for support-message push alerts. Throws if the user denies permission. */
export async function enableSupportPush(): Promise<void> {
  if (!pushSupported()) throw new Error("Push notifications aren't supported here.");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notification permission was denied.");

  const reg = await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY) as BufferSource,
    }));

  await subscribeToSupportPush(sub.toJSON() as any);
}

export async function disableSupportPush(): Promise<void> {
  if (!pushSupported()) return;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  await unsubscribeFromSupportPush(sub.endpoint).catch(() => {});
  await sub.unsubscribe();
}
