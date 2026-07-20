import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  conversationReply,
  conversationText,
  writingBooks,
  type ConvCorrection,
  type ConvMessage,
  type WritingBook,
} from "../auth/api";

const LANGS = [
  { code: "de", name: "German",  speech: "de-DE" },
  { code: "en", name: "English", speech: "en-US" },
  { code: "fr", name: "French",  speech: "fr-FR" },
  { code: "es", name: "Spanish", speech: "es-ES" },
  { code: "it", name: "Italian", speech: "it-IT" },
];

const FALLBACK_TEXTS: Record<string, string[]> = {
  de: [
    "Heute Morgen bin ich früh aufgestanden. Nach dem Frühstück bin ich zur Arbeit gegangen. Am Abend habe ich mit einem Freund Kaffee getrunken.",
    "Das Wetter ist heute sehr schön. Ich gehe gerne in den Park und lese ein Buch. Die Vögel singen und die Sonne scheint hell.",
    "Letzte Woche habe ich einen neuen Film gesehen. Die Geschichte war sehr interessant. Ich empfehle ihn allen meinen Freunden.",
    "Jeden Morgen trinke ich eine Tasse Kaffee und lese die Nachrichten. Dann fahre ich mit dem Fahrrad zur Arbeit. Der Weg dauert ungefähr zwanzig Minuten.",
    "Am Wochenende bin ich mit meiner Familie in die Berge gefahren. Wir haben gewandert und frische Luft genossen. Abends haben wir in einer kleinen Hütte gegessen.",
    "Mein Lieblingsrestaurant liegt in der Nähe des Bahnhofs. Das Essen dort ist immer frisch und lecker. Ich gehe oft mit meinen Kollegen dorthin.",
  ],
  en: [
    "This morning I woke up early. After breakfast, I went to work. In the evening, I had coffee with a friend.",
    "The weather is beautiful today. I like going to the park and reading a book. The birds are singing and the sun is shining.",
    "Last week I watched a new film. The story was very interesting. I recommend it to all my friends.",
    "Every morning I drink a cup of coffee and read the news. Then I cycle to work. The journey takes about twenty minutes.",
    "Last weekend I went hiking with my family. We enjoyed the fresh air and beautiful views. In the evening we had dinner at a small restaurant.",
  ],
  fr: [
    "Ce matin, je me suis réveillé tôt. Après le petit-déjeuner, je suis allé au travail. Le soir, j'ai pris un café avec un ami.",
    "Le temps est très beau aujourd'hui. J'aime me promener dans le parc et lire un livre. Les oiseaux chantent et le soleil brille.",
    "La semaine dernière, j'ai commencé à apprendre une nouvelle recette. J'ai fait une soupe de légumes simple mais délicieuse.",
  ],
  es: [
    "Esta mañana me desperté temprano. Después del desayuno, fui al trabajo. Por la tarde, tomé un café con un amigo.",
    "El tiempo está muy bonito hoy. Me gusta ir al parque y leer un libro. Los pájaros cantan y el sol brilla.",
    "El fin de semana pasado fui de excursión con mi familia. Disfrutamos del aire fresco y las vistas. Por la noche cenamos en un pequeño restaurante.",
  ],
  it: [
    "Stamattina mi sono svegliato presto. Dopo colazione, sono andato al lavoro. La sera, ho preso un caffè con un amico.",
    "Il tempo è molto bello oggi. Mi piace andare al parco e leggere un libro. Gli uccelli cantano e il sole splende.",
    "Il fine settimana scorso sono andato in montagna con la mia famiglia. Abbiamo fatto escursioni e respirato aria fresca.",
  ],
};

function randomFallback(langCode: string): string {
  const pool = FALLBACK_TEXTS[langCode] ?? FALLBACK_TEXTS.en;
  return pool[Math.floor(Math.random() * pool.length)];
}

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
  const [readSource, setReadSource] = useState<string | null>(null);
  const [readBookTitle, setReadBookTitle] = useState<string | null>(null);
  const [readBusy, setReadBusy] = useState(false);
  const [readListening, setReadListening] = useState(false);
  const [readResult, setReadResult] = useState<WordResult[] | null>(null);
  const [readError, setReadError] = useState<string | null>(null);
  const readRecRef = useRef<any>(null);

  // Books for reading tab
  const [readBooks, setReadBooks] = useState<WritingBook[]>([]);
  const [selectedReadBookId, setSelectedReadBookId] = useState<number | null>(null);

  // Load books when reading tab is opened
  useEffect(() => {
    if (tab !== "read") return;
    writingBooks()
      .then((list) => {
        setReadBooks(list);
        if (list.length > 0 && !selectedReadBookId) setSelectedReadBookId(list[0].id);
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

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
    setReadSource(null);
    setReadBookTitle(null);
    setReadError(null);
    try {
      const res = await conversationText({
        language: langCode,
        ...(selectedReadBookId ? { book_id: selectedReadBookId } : {}),
      });
      setReadText(res.text);
      setReadSource(res.source);
      setReadBookTitle(res.book_title ?? null);
    } catch {
      setReadText(randomFallback(langCode));
      setReadSource("fallback");
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
          {readBooks.length > 0 && (
            <div className="writing__book-selector">
              <label className="cardeditor__field">
                <span>{t("writing.selectBook")}</span>
                <select
                  className="input"
                  value={selectedReadBookId ?? ""}
                  onChange={(e) => setSelectedReadBookId(Number(e.target.value))}
                >
                  <option value="">{t("conversation.autoSource")}</option>
                  {readBooks.map((b) => (
                    <option key={b.id} value={b.id}>{b.title}</option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <div className="conv__read-actions">
            <button className="btn btn--primary" disabled={readBusy} onClick={fetchReadText}>
              {readBusy ? t("conversation.fetchingText") : t("conversation.fetchText")}
            </button>
          </div>

          {readError && <p className="auth__error">{readError}</p>}

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
                <div className="conv__read-footer">
                  <button className="btn btn--ghost btn--sm conv__play" onClick={() => speak(readText)}>
                    ▶ {t("conversation.listenBtn")}
                  </button>
                  {readSource === "books" && readBookTitle && (
                    <span className="writing__prompt-source">📚 {readBookTitle}</span>
                  )}
                </div>
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
