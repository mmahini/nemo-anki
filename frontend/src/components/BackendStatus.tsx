import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

/** Banner shown while API calls are failing and being retried (the
 * "nemo:waking" window event from the API layer). In practice the usual cause
 * is the user's route to the server — filtered/unstable internet or a VPN —
 * so the message points there rather than blaming the server. */
export default function BackendStatus() {
  const { t } = useTranslation();
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    const onWaking = (e: Event) => setWaking((e as CustomEvent).detail === true);
    window.addEventListener("nemo:waking", onWaking);
    return () => window.removeEventListener("nemo:waking", onWaking);
  }, []);

  if (!waking) return null;

  return (
    <div className="wakebanner" role="status" aria-live="polite">
      <span className="wakebanner__spinner" aria-hidden="true" />
      <span>{t("backendStatus.connectionTrouble")}</span>
    </div>
  );
}
