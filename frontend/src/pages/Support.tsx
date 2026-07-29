import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchSupportThread, sendSupportMessage, type SupportMessage } from "../auth/api";

const POLL_MS = 5000;
const TEXTAREA_MAX_PX = 120;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function Support() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, TEXTAREA_MAX_PX) + "px";
  }

  async function handleSend() {
    const trimmed = inputText.trim();
    if (!trimmed || sending) return;

    // Optimistic bubble — shows instantly instead of waiting on the round trip.
    const optimisticId = -Date.now();
    setMessages((prev) => [
      ...prev,
      { id: optimisticId, from_admin: false, body: trimmed, created_at: new Date().toISOString() },
    ]);
    setInputText("");
    requestAnimationFrame(autoResize);
    setSending(true);
    setError(null);
    try {
      const thread = await sendSupportMessage(trimmed);
      setMessages(thread.messages);
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
      setInputText(trimmed);
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="support">
      <div className="support__header">
        <span className="support__badge" aria-hidden>🎧</span>
        <div>
          <h1>{t("support.title")}</h1>
          <p className="import__sub">{t("support.subtitle")}</p>
        </div>
      </div>

      <div className="panel support__chat">
        {loading && <p className="support__loading">{t("common.loading")}</p>}
        {!loading && messages.length === 0 && (
          <div className="support__empty">
            <span className="support__empty-icon" aria-hidden>💬</span>
            <p>{t("support.emptyHint")}</p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`support__msg support__msg--${msg.from_admin ? "admin" : "user"}`}
          >
            {msg.from_admin && <span className="support__avatar" aria-hidden>🎧</span>}
            <div className="support__msg-body">
              <div className="support__bubble">
                <span dir="auto">{msg.body}</span>
              </div>
              <span className="support__time">{formatTime(msg.created_at)}</span>
            </div>
          </div>
        ))}
        {error && <p className="auth__error">{error}</p>}
        <div ref={messagesEndRef} />
      </div>

      <div className="support__input">
        <textarea
          ref={textareaRef}
          className="input support__text-input"
          rows={1}
          placeholder={t("support.inputPlaceholder")}
          value={inputText}
          onChange={(e) => {
            setInputText(e.target.value);
            autoResize();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button
          className="support__send"
          onClick={handleSend}
          disabled={sending || !inputText.trim()}
          aria-label={t("support.sendBtn")}
          title={t("support.sendBtn")}
        >
          ➤
        </button>
      </div>
    </div>
  );
}
