import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { updateMe } from "../auth/api";
import { applyLanguage } from "../i18n";

/** Nemo — the guide. Rendered in a circle, which is also what keeps the source
 * image's corner watermark out of frame. */
function Nemo({ size = 108 }: { size?: number }) {
  return (
    <img
      className="nemo"
      src="/nemo-character.webp"
      width={size}
      height={size}
      alt=""
      /* Decorative: every step's meaning is carried by its text. */
      aria-hidden
    />
  );
}

/** One thing the app does, listed on the tour step. */
function Feature({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <li className="wfeature">
      <span className="wfeature__icon" aria-hidden>{icon}</span>
      <div>
        <strong className="wfeature__title">{title}</strong>
        <span className="wfeature__body">{body}</span>
      </div>
    </li>
  );
}

/**
 * First-run walkthrough. The order matters: language comes first, so every
 * following step is already in the language the user picked, then the name, then
 * the concepts they need before the deck list makes any sense (a deck, a card,
 * what grading does) and finally what else is here.
 *
 * Reachable at /welcome forever, so the account menu can replay it.
 */
export default function Welcome() {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [name, setName] = useState(user?.display_name ?? "");
  const [lang, setLang] = useState<"en" | "fa">(user?.ui_language ?? "en");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Apply the language immediately so the very next step is already in it; the
   * server write can lag behind without the UI waiting on it. */
  function pickLanguage(code: "en" | "fa") {
    setLang(code);
    applyLanguage(code);
    updateMe({ ui_language: code }).catch(() => {});
    setStep(1);
  }

  async function finish() {
    setSaving(true);
    setError(null);
    try {
      await updateMe({
        display_name: name.trim(),
        ui_language: lang,
        onboarded: true,
      });
      await refreshUser();
      navigate("/app", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
      setSaving(false);
    }
  }

  const firstName = name.trim().split(/\s+/)[0];

  // Step 0 is bilingual by necessity — we don't know yet which language to use.
  const steps: ReactNode[] = [
    <div className="wstep wstep--lang" key="lang">
      <Nemo size={132} />
      {/* Each line carries its own dir: replaying this step from a Persian UI
          would otherwise render the English "?" at the wrong end. */}
      <h1 className="wstep__title">
        <span dir="ltr" lang="en">Hi, I&apos;m Nemo</span>
        <span dir="rtl" lang="fa">سلام، من نمو هستم</span>
      </h1>
      <p className="wstep__lede">
        <span dir="ltr" lang="en">Which language should the app be in?</span>
        <span dir="rtl" lang="fa">اپ به کدام زبان باشد؟</span>
      </p>
      <div className="wlangs">
        <button className="wlang" onClick={() => pickLanguage("en")} dir="ltr" lang="en">
          <span className="wlang__name">English</span>
          <span className="wlang__note">Continue in English</span>
        </button>
        <button className="wlang" onClick={() => pickLanguage("fa")} dir="rtl" lang="fa">
          <span className="wlang__name">فارسی</span>
          <span className="wlang__note">ادامه به فارسی</span>
        </button>
      </div>
    </div>,

    <div className="wstep" key="name">
      <Nemo />
      <h1 className="wstep__title">{t("welcome.nameTitle")}</h1>
      <p className="wstep__lede">{t("welcome.nameLede")}</p>
      <input
        className="input wname"
        autoFocus
        maxLength={40}
        value={name}
        placeholder={t("welcome.namePlaceholder")}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && name.trim() && setStep(2)}
      />
    </div>,

    <div className="wstep" key="decks">
      <Nemo />
      <h1 className="wstep__title">
        {firstName ? t("welcome.decksTitleNamed", { name: firstName }) : t("welcome.decksTitle")}
      </h1>
      <p className="wstep__lede">{t("welcome.decksLede")}</p>
      <div className="wdemo">
        <div className="wdemo__deck">
          <span className="wdemo__deckname">🇩🇪 German</span>
          <span className="wdemo__deckmeta">{t("welcome.demoDeckMeta")}</span>
        </div>
        <div className="wdemo__card">
          <span className="wdemo__cardface">der Tisch</span>
          <span className="wdemo__carddiv" aria-hidden />
          <span className="wdemo__cardback">{t("welcome.demoCardBack")}</span>
        </div>
      </div>
      <p className="wstep__note">{t("welcome.decksNote")}</p>
    </div>,

    <div className="wstep" key="review">
      <Nemo />
      <h1 className="wstep__title">{t("welcome.reviewTitle")}</h1>
      <p className="wstep__lede">{t("welcome.reviewLede")}</p>
      <div className="wgrades">
        <span className="wgrade wgrade--again">{t("study.again")}</span>
        <span className="wgrade wgrade--hard">{t("study.hard")}</span>
        <span className="wgrade wgrade--good">{t("study.good")}</span>
        <span className="wgrade wgrade--easy">{t("study.easy")}</span>
      </div>
      <p className="wstep__note">{t("welcome.reviewNote")}</p>
    </div>,

    <div className="wstep" key="tour">
      <Nemo />
      <h1 className="wstep__title">{t("welcome.tourTitle")}</h1>
      <p className="wstep__lede">{t("welcome.tourLede")}</p>
      <ul className="wfeatures">
        <Feature icon="↓" title={t("welcome.featImportTitle")} body={t("welcome.featImportBody")} />
        <Feature icon="📖" title={t("welcome.featBooksTitle")} body={t("welcome.featBooksBody")} />
        <Feature icon="🎙" title={t("welcome.featPracticeTitle")} body={t("welcome.featPracticeBody")} />
        <Feature icon="📊" title={t("welcome.featStatsTitle")} body={t("welcome.featStatsBody")} />
      </ul>
    </div>,
  ];

  const last = step === steps.length - 1;

  return (
    <main className="welcome">
      <div className="welcome__card">
        {/* The language step has its own buttons, so it shows no chrome. */}
        {step > 0 && (
          <div className="wprogress" role="progressbar" aria-valuenow={step + 1} aria-valuemin={1} aria-valuemax={steps.length}>
            {steps.map((_, i) => (
              <span key={i} className={`wprogress__dot ${i <= step ? "is-done" : ""}`} />
            ))}
          </div>
        )}

        {steps[step]}

        {error && <p className="auth__error">{error}</p>}

        {step > 0 && (
          <div className="welcome__actions">
            <button className="btn btn--ghost" onClick={() => setStep(step - 1)} disabled={saving}>
              {t("welcome.back")}
            </button>
            {last ? (
              <button className="btn btn--primary btn--lg" onClick={finish} disabled={saving}>
                {saving ? t("welcome.saving") : t("welcome.start")}
              </button>
            ) : (
              <button
                className="btn btn--primary btn--lg"
                onClick={() => setStep(step + 1)}
                /* The name is the one thing we actually ask for — don't move on
                   without it, rather than silently storing an empty name. */
                disabled={step === 1 && !name.trim()}
              >
                {t("welcome.next")}
              </button>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
