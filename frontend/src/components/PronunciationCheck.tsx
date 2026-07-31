import { useState } from "react";
import { useTranslation } from "react-i18next";

import { isPronunciationMatch, listenOnce, sttSupported } from "../lib/pronunciation";
import { playCorrectSound, playWrongSound } from "../lib/sound";
import { stopSpeaking } from "../lib/tts";

type Status = "idle" | "listening" | "correct" | "wrong";

type Props = {
  text: string;
  lang: string;
  /** Small variant for inline use next to a small SpeakButton (reading/plural/example rows). */
  small?: boolean;
};

/** 🎤 button, meant to sit next to a SpeakButton: records one utterance,
 * compares it against `text`, and gives audio + visual feedback. Hidden when
 * the browser has no SpeechRecognition, or there's nothing to pronounce. */
export default function PronunciationCheck({ text, lang, small }: Props) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Status>("idle");
  const [heard, setHeard] = useState("");

  if (!text?.trim() || !sttSupported()) return null;

  async function record() {
    if (status === "listening") return;
    stopSpeaking(); // don't let the mic hear the 🔊 button's own playback
    setStatus("listening");
    setHeard("");
    try {
      const transcript = await listenOnce(lang);
      setHeard(transcript);
      const ok = isPronunciationMatch(text, transcript);
      setStatus(ok ? "correct" : "wrong");
      if (ok) playCorrectSound();
      else playWrongSound();
      setTimeout(() => setStatus("idle"), 2200);
    } catch {
      setStatus("idle");
    }
  }

  return (
    <div className="pron">
      <button
        type="button"
        className={`pron__btn ${small ? "pron__btn--sm" : ""} pron__btn--${status}`}
        onClick={record}
        disabled={status === "listening"}
        title={t("study.pronounceHint")}
        aria-label={t("study.pronounceHint")}
      >
        {status === "listening" ? "🎙️" : "🎤"}
      </button>
      {status === "correct" && <span className="pron__result pron__result--ok">{t("study.pronounceCorrect")}</span>}
      {status === "wrong" && (
        <span className="pron__result pron__result--bad">
          {t("study.pronounceWrong")}{heard && ` (${heard})`}
        </span>
      )}
    </div>
  );
}
