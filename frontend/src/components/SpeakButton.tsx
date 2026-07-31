import { useTranslation } from "react-i18next";

import { canSpeak, speak } from "../lib/tts";

type Props = {
  text: string;
  lang: string;
  /** Small variant for inline use next to readings. */
  small?: boolean;
  title?: string;
};

/** A 🔊 button that reads `text` aloud in `lang` using the Web Speech API. */
export default function SpeakButton({ text, lang, small, title }: Props) {
  const { t } = useTranslation();
  if (!text?.trim() || !canSpeak()) return null;
  return (
    <button
      type="button"
      className={`speak ${small ? "speak--sm" : ""}`}
      title={title ?? t("common.listen")}
      aria-label={title ?? t("common.listen")}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        speak(text, lang);
      }}
    >
      🔊
    </button>
  );
}
