import { pushSubscribe, pushUnsubscribe } from "../auth/api";

/** Converts the VAPID public key (URL-safe base64) into the Uint8Array
 * shape `pushManager.subscribe()` expects — the standard, widely-used
 * conversion, since the Push API only accepts a raw applicationServerKey. */
function urlBase64ToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** Requests notification permission (if needed) and registers this browser's
 * push subscription with the backend. Throws if permission is denied or the
 * browser doesn't support push. */
export async function subscribeToPush(): Promise<void> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("push-unsupported");
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("permission-denied");
  }
  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(import.meta.env.VITE_VAPID_PUBLIC_KEY),
    });
  }
  const json = subscription.toJSON();
  await pushSubscribe({ endpoint: json.endpoint!, p256dh: json.keys!.p256dh, auth: json.keys!.auth });
}

/** True if this browser already has push permission and an active subscription. */
export async function hasPushSubscription(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return subscription !== null;
}

export async function unsubscribeFromPush(): Promise<void> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;
  await pushUnsubscribe(subscription.endpoint);
  await subscription.unsubscribe();
}
