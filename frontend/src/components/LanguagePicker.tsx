import { useTranslation } from "react-i18next";

import { LANGUAGES } from "../lib/languages";

/** The two-part language question, shared by onboarding and the reels feed.
 *
 * Two lists, because content carries two languages: a reel teaches a target
 * language *in* a base language. Asking only "what are you learning?" would let
 * us hand a German learner clips narrated in a language they can't read.
 *
 * Multi-select on both sides on purpose — people learn more than one language,
 * and most already read more than one.
 */
export default function LanguagePicker({
  learning,
  known,
  onChange,
}: {
  learning: string[];
  known: string[];
  onChange: (next: { learning: string[]; known: string[] }) => void;
}) {
  const { t } = useTranslation();

  function toggle(list: string[], code: string): string[] {
    return list.includes(code) ? list.filter((c) => c !== code) : [...list, code];
  }

  return (
    <div className="langpick">
      <fieldset className="langpick__group">
        <legend className="langpick__legend">{t("languages.learningLabel")}</legend>
        <p className="langpick__hint">{t("languages.learningHint")}</p>
        <div className="langpick__chips">
          {LANGUAGES.map((lang) => (
            <button
              type="button"
              key={`learn-${lang.code}`}
              className={`langchip${learning.includes(lang.code) ? " langchip--on" : ""}`}
              aria-pressed={learning.includes(lang.code)}
              onClick={() => onChange({ learning: toggle(learning, lang.code), known })}
            >
              {lang.endonym}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="langpick__group">
        <legend className="langpick__legend">{t("languages.knownLabel")}</legend>
        <p className="langpick__hint">{t("languages.knownHint")}</p>
        <div className="langpick__chips">
          {LANGUAGES.map((lang) => (
            <button
              type="button"
              key={`known-${lang.code}`}
              className={`langchip${known.includes(lang.code) ? " langchip--on" : ""}`}
              aria-pressed={known.includes(lang.code)}
              onClick={() => onChange({ learning, known: toggle(known, lang.code) })}
            >
              {lang.endonym}
            </button>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
