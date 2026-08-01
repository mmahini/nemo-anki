import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { applyPwaUpdate, pwaUpdateReady, PWA_UPDATE_EVENT } from "../pwa";

/** "New version available" toast. Shown when the service worker has a fresh
 * deployment downloaded and waiting; the button activates it and reloads. */
export default function UpdateToast() {
  const { t } = useTranslation();
  const [ready, setReady] = useState(pwaUpdateReady);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onUpdate = () => setReady(true);
    window.addEventListener(PWA_UPDATE_EVENT, onUpdate);
    return () => window.removeEventListener(PWA_UPDATE_EVENT, onUpdate);
  }, []);

  if (!ready) return null;

  function update() {
    setBusy(true);
    // Reloads the page on success; only a failure leaves us here.
    applyPwaUpdate().catch(() => setBusy(false));
  }

  return (
    <div className="updatetoast" role="status" aria-live="polite">
      <span className="updatetoast__msg">✨ {t("pwa.updateReady")}</span>
      <button className="btn btn--primary" onClick={update} disabled={busy}>
        {busy ? t("pwa.updating") : t("pwa.updateBtn")}
      </button>
    </div>
  );
}
