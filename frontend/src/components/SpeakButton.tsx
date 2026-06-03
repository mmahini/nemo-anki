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
  if (!text.trim() || !canSpeak()) return null;
  return (
    <button
      type="button"
      className={`speak ${small ? "speak--sm" : ""}`}
      title={title ?? "Listen"}
      aria-label="Listen"
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
