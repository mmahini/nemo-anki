import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchSupportThread, sendSupportMessage, type SupportMessage } from "../auth/api";

const POLL_MS = 5000;

export default function Support() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSupportThread()
      .then((thread) => {
        if (!cancelled) setMessages(thread.messages);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : t("common.error"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    const id = window.setInterval(() => {
      fetchSupportThread()
        .then((thread) => {
          if (!cancelled) setMessages(thread.messages);
        })
        .catch(() => {});
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const trimmed = inputText.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError(null);
    try {
      const thread = await sendSupportMessage(trimmed);
      setMessages(thread.messages);
      setInputText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="conversation">
      <h1>{t("support.title")}</h1>
      <p className="import__sub">{t("support.subtitle")}</p>

      <div className="panel conv__chat">
        {loading && <p className="conv__hint">{t("common.loading")}</p>}
        {!loading && messages.length === 0 && (
          <p className="conv__hint">{t("support.emptyHint")}</p>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`conv__msg conv__msg--${msg.from_admin ? "ai" : "user"}`}>
            <div className="conv__bubble">
              <span dir="auto">{msg.body}</span>
            </div>
          </div>
        ))}
        {error && <p className="auth__error">{error}</p>}
        <div ref={messagesEndRef} />
      </div>

      <div className="conv__input">
        <input
          className="input conv__text-input"
          placeholder={t("support.inputPlaceholder")}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={sending}
        />
        <button
          className="btn btn--primary"
          onClick={handleSend}
          disabled={sending || !inputText.trim()}
        >
          {t("support.sendBtn")}
        </button>
      </div>
    </div>
  );
}
