import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  conversationReply,
  type ConvCorrection,
  type ConvMessage,
} from "../../auth/api";
import { findLang } from "./languages";
import { useSpeech } from "./useSpeech";

/** Free chat with the AI in the target language: speak or type, it replies aloud
 * and flags what you got wrong. */
export default function SpeakPanel({ language }: { language: string }) {
  const { t } = useTranslation();
  const lang = findLang(language);
  const { supported, listening, speak, toggle } = useSpeech(lang.speech);

  const [messages, setMessages] = useState<ConvMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // Switching target language mid-thread would give the AI a mixed history.
  useEffect(() => {
    setMessages([]);
    setError(null);
  }, [language]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    setMessages((prev) => [...prev, { role: "user", text: trimmed }]);
    setInputText("");
    setBusy(true);
    setError(null);
    try {
      const reply = await conversationReply({ language, text: trimmed, history });
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: reply.response, corrections: reply.corrections },
      ]);
      if (reply.response) speak(reply.response);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="speakpanel">
      {!supported && (
        <div className="panel panel--error conv__nospeech">{t("conversation.noSpeechSupport")}</div>
      )}

      <div className="panel conv__chat">
        {messages.length === 0 && !busy && (
          <p className="conv__hint">
            {supported
              ? t("conversation.speakHint", { lang: lang.name })
              : t("practice.typeHint", { lang: lang.name })}
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`conv__msg conv__msg--${msg.role}`}>
            <div className="conv__bubble">
              <span dir="auto">{msg.text}</span>
              {msg.role === "ai" && (
                <button
                  className="btn btn--ghost btn--sm conv__play"
                  onClick={() => speak(msg.text)}
                  title={t("conversation.playBtn")}
                  aria-label={t("conversation.playBtn")}
                >
                  ▶
                </button>
              )}
            </div>
            {msg.corrections && msg.corrections.length > 0 && (
              <div className="conv__corrections">
                {msg.corrections.map((c: ConvCorrection, j) => (
                  <div key={j} className="conv__correction">
                    <span className="issue__bad">✗ {c.original}</span>
                    <span className="issue__good">✓ {c.correction}</span>
                    {c.explanation && <span className="issue__why">{c.explanation}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <p className="conv__hint">{t("conversation.thinking")}</p>}
        {error && <p className="auth__error">{error}</p>}
        <div ref={endRef} />
      </div>

      <div className="composer">
        {supported && (
          <button
            className={`btn btn--ghost conv__mic${listening ? " conv__mic--active" : ""}`}
            onClick={() => toggle((txt) => send(txt))}
            disabled={busy}
            title={listening ? t("conversation.stopBtn") : t("conversation.micBtn")}
            aria-label={listening ? t("conversation.stopBtn") : t("conversation.micBtn")}
          >
            {listening ? "⏹" : "🎙"}
          </button>
        )}
        <input
          className="input composer__input"
          placeholder={listening ? t("conversation.listening") : t("conversation.inputPlaceholder")}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(inputText);
            }
          }}
          disabled={busy || listening}
        />
        <button
          className="btn btn--primary"
          onClick={() => send(inputText)}
          disabled={busy || listening || !inputText.trim()}
        >
          {t("conversation.sendBtn")}
        </button>
      </div>

      {messages.length > 0 && (
        <button
          className="btn btn--ghost btn--sm conv__reset"
          onClick={() => {
            setMessages([]);
            setError(null);
          }}
        >
          {t("conversation.newConv")}
        </button>
      )}
    </div>
  );
}
