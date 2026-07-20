import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  conversationReply,
  conversationText,
  type ConvCorrection,
  type ConvMessage,
} from "../auth/api";

const LANGS = [
  { code: "de", name: "German",  speech: "de-DE" },
  { code: "en", name: "English", speech: "en-US" },
  { code: "fr", name: "French",  speech: "fr-FR" },
  { code: "es", name: "Spanish", speech: "es-ES" },
  { code: "it", name: "Italian", speech: "it-IT" },
];

type Tab = "chat" | "read";
type WordResult = { word: string; ok: boolean };

function diffWords(original: string, spoken: string): WordResult[] {
  const clean = (s: string) => s.toLowerCase().replace(/[.,!?;:'"„"«»]/g, "");
  const spokenSet = new Set(spoken.trim().split(/\s+/).map(clean));
  return original.trim().split(/\s+/).map((w) => ({ word: w, ok: spokenSet.has(clean(w)) }));
}

export default function Conversation() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("chat");
  const [langCode, setLangCode] = useState("de");

  // Chat state
  const [messages, setMessages] = useState<ConvMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [listening, setListening] = useState(false);
  const [busyChat, setBusyChat] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recRef = useRef<any>(null);

  // Reading state
  const [readText, setReadText] = useState<string | null>(null);
  const [readBusy, setReadBusy] = useState(false);
  const [readListening, setReadListening] = useState(false);
  const [readResult, setReadResult] = useState<WordResult[] | null>(null);
  const readRecRef = useRef<any>(null);

  const lang = LANGS.find((l) => l.code === langCode) ?? LANGS[0];
  const hasSpeech =
    typeof window !== "undefined" &&
    ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busyChat]);

  function speak(text: string) {
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.lang = lang.speech;
    utt.rate = 0.9;
    window.speechSynthesis.speak(utt);
  }

  function startRec(
    onResult: (txt: string) => void,
    refHolder: React.MutableRefObject<any>,
    setActive: (v: boolean) => void,
  ) {
    const SpeechRec =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const rec = new SpeechRec();
    rec.lang = lang.speech;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    refHolder.current = rec;
    rec.onresult = (e: any) => onResult(e.results[0][0].transcript);
    rec.onend = () => setActive(false);
    rec.onerror = () => setActive(false);
    rec.start();
    setActive(true);
  }

  // ── Chat ─────────────────────────────────────────────────────────────────
  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const userMsg: ConvMessage = { role: "user", text: trimmed };
    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setBusyChat(true);
    setChatError(null);
    try {
      const reply = await conversationReply({ language: langCode, text: trimmed, history });
      const aiMsg: ConvMessage = {
        role: "ai",
        text: reply.response,
        corrections: reply.corrections,
      };
      setMessages((prev) => [...prev, aiMsg]);
      if (reply.response) speak(reply.response);
    } catch (e) {
      setChatError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setBusyChat(false);
    }
  }

  function handleMic() {
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    startRec((txt) => sendMessage(txt), recRef, setListening);
  }

  // ── Reading ───────────────────────────────────────────────────────────────
  async function fetchReadText() {
    setReadBusy(true);
    setReadResult(null);
    setReadText(null);
    try {
      const res = await conversationText({ language: langCode });
      setReadText(res.text);
    } catch {
      // leave readText null — user can try again
    } finally {
      setReadBusy(false);
    }
  }

  function handleReadMic() {
    if (readListening) {
      readRecRef.current?.stop();
      setReadListening(false);
      return;
    }
    if (!readText) return;
    startRec(
      (spoken) => setReadResult(diffWords(readText, spoken)),
      readRecRef,
      setReadListening,
    );
  }

  function onLangChange(code: string) {
    setLangCode(code);
    setMessages([]);
    setChatError(null);
    setReadText(null);
    setReadResult(null);
  }

  const correctCount = readResult ? readResult.filter((w) => w.ok).length : 0;

  return (
    <div className="conversation">
      <h1>{t("conversation.title")}</h1>
      <p className="import__sub">{t("conversation.subtitle")}</p>

      {/* Top bar: language + tab toggle */}
      <div className="conv__bar">
        <label className="cardeditor__field">
          <span>{t("conversation.languageLabel")}</span>
          <select className="input" value={langCode} onChange={(e) => onLangChange(e.target.value)}>
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>{l.name}</option>
            ))}
          </select>
        </label>
        <div className="conv__tabs">
          <button
            className={`btn btn--sm ${tab === "chat" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setTab("chat")}
          >
            {t("conversation.chatTab")}
          </button>
          <button
            className={`btn btn--sm ${tab === "read" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setTab("read")}
          >
            {t("conversation.readTab")}
          </button>
        </div>
      </div>

      {!hasSpeech && (
        <div className="panel panel--error conv__nospeech">
          {t("conversation.noSpeechSupport")}
        </div>
      )}

      {/* ── CHAT TAB ── */}
      {tab === "chat" && (
        <>
          <div className="panel conv__chat">
            {messages.length === 0 && !busyChat && (
              <p className="conv__hint">{t("conversation.speakHint", { lang: lang.name })}</p>
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
            {busyChat && <p className="conv__hint">{t("conversation.thinking")}</p>}
            {chatError && <p className="auth__error">{chatError}</p>}
            <div ref={messagesEndRef} />
          </div>

          <div className="conv__input">
            {hasSpeech && (
              <button
                className={`btn btn--ghost conv__mic${listening ? " conv__mic--active" : ""}`}
                onClick={handleMic}
                disabled={busyChat}
                title={listening ? t("conversation.stopBtn") : t("conversation.micBtn")}
              >
                {listening ? "⏹" : "🎙"}
              </button>
            )}
            <input
              className="input conv__text-input"
              placeholder={t("conversation.inputPlaceholder")}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage(inputText);
                }
              }}
              disabled={busyChat || listening}
            />
            <button
              className="btn btn--primary"
              onClick={() => sendMessage(inputText)}
              disabled={busyChat || listening || !inputText.trim()}
            >
              {t("conversation.sendBtn")}
            </button>
          </div>

          {messages.length > 0 && (
            <button
              className="btn btn--ghost btn--sm conv__reset"
              onClick={() => { setMessages([]); setChatError(null); }}
            >
              {t("conversation.newConv")}
            </button>
          )}
        </>
      )}

      {/* ── READING TAB ── */}
      {tab === "read" && (
        <>
          <div className="conv__read-actions">
            <button className="btn btn--primary" disabled={readBusy} onClick={fetchReadText}>
              {readBusy ? t("conversation.fetchingText") : t("conversation.fetchText")}
            </button>
          </div>

          {readText && (
            <>
              <div className="panel conv__read-panel">
                {readResult ? (
                  <p className="conv__read-text">
                    {readResult.map((wr, i) => (
                      <span key={i} className={`conv__word conv__word--${wr.ok ? "ok" : "bad"}`}>
                        {wr.word}{" "}
                      </span>
                    ))}
                  </p>
                ) : (
                  <p className="conv__read-text" dir="auto">{readText}</p>
                )}
                <button
                  className="btn btn--ghost btn--sm conv__play"
                  onClick={() => speak(readText)}
                >
                  ▶ {t("conversation.listenBtn")}
                </button>
              </div>

              <div className="conv__read-controls">
                {hasSpeech && (
                  <button
                    className={`btn conv__mic${readListening ? " btn--ghost conv__mic--active" : " btn--primary"}`}
                    onClick={handleReadMic}
                  >
                    {readListening
                      ? `⏹ ${t("conversation.stopReading")}`
                      : `🎙 ${t("conversation.startReading")}`}
                  </button>
                )}
                {readResult && (
                  <button className="btn btn--ghost btn--sm" onClick={() => setReadResult(null)}>
                    {t("conversation.tryAgain")}
                  </button>
                )}
              </div>

              {readResult && (
                <p className="conv__read-stats">
                  {correctCount}/{readResult.length} {t("conversation.correct")}
                </p>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
