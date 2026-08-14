import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { isIOS, isStandalone, retryLastSpeak, SPEECH_FAILED_EVENT } from "../lib/tts";

/** Shown when a 🔊 press made no sound at all.
 *
 * Reading a card aloud is audio *output*, so there is no permission behind it
 * and no prompt to re-grant — on iOS the cause is almost always the physical
 * Ring/Silent switch, which mutes web audio and the speech synthesiser alike
 * and cannot be detected or overridden from a web page. So this explains the
 * likely cause and offers a retry: the retry click is a fresh user gesture,
 * which is by itself enough to unlock playback in some iOS states. */
export default function SpeechHelp() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onFail = () => setOpen(true);
    window.addEventListener(SPEECH_FAILED_EVENT, onFail);
    return () => window.removeEventListener(SPEECH_FAILED_EVENT, onFail);
  }, []);

  if (!open) return null;

  const ios = isIOS();
  const steps = ios
    ? [
        t("speechHelp.iosSilentSwitch"),
        t("speechHelp.iosVolume"),
        ...(isStandalone() ? [t("speechHelp.iosReopen")] : []),
      ]
    : [t("speechHelp.genericVolume"), t("speechHelp.genericOffline")];

  function retry() {
    setOpen(false);
    retryLastSpeak();
  }

  return (
    <div className="speechhelp" role="alertdialog" aria-live="assertive" aria-label={t("speechHelp.title")}>
      <div className="speechhelp__body">
        <strong className="speechhelp__title">🔇 {t("speechHelp.title")}</strong>
        <p className="speechhelp__lead">{t("speechHelp.lead")}</p>
        <ul className="speechhelp__steps">
          {steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </div>
      <div className="speechhelp__actions">
        <button className="btn btn--primary" onClick={retry}>
          {t("speechHelp.retry")}
        </button>
        <button className="btn btn--ghost" onClick={() => setOpen(false)}>
          {t("speechHelp.dismiss")}
        </button>
      </div>
    </div>
  );
}
