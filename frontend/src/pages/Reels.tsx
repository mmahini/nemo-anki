import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Link } from "react-router-dom";

import {
  fetchReels,
  fetchSavedReels,
  makeCardsFromReel,
  markReelSeen,
  suggestReelSource,
  toggleReelSaved,
  updateMe,
  type Reel,
} from "../auth/api";
import { useAuth } from "../auth/AuthContext";
import LanguagePicker from "../components/LanguagePicker";
import { LANGUAGES } from "../lib/languages";

const LANG_KEY = "nemo-anki.reels-lang";
const LANG_HINT_KEY = "nemo-anki.reels-lang-hint";

function languageEndonym(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.endonym ?? code;
}

/** Short videos from language-teaching accounts, plus our own — presented the
 * way people already know from Instagram: a full-screen vertical feed, one
 * reel per screen, snap scrolling, the visible one playing.
 *
 * Playback is a plain <video> off our own CDN — no Instagram embed, which
 * would render an empty box for anyone behind the block that made us host the
 * files in the first place.
 *
 * `preload="none"` still matters: at ~3 MB a reel only the on-screen video
 * downloads. Scrolling *to* a reel is the user asking for it; scrolling past
 * doesn't fetch the ones below.
 *
 * Autoplay starts muted because browsers refuse anything else without a
 * gesture; one tap on the sound button unmutes the whole session.
 */
export default function Reels() {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();

  const [reels, setReels] = useState<Reel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsPrefs, setNeedsPrefs] = useState(false);
  const [caughtUp, setCaughtUp] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);

  /** Which reel the viewport has settled on (drives play/pause). */
  const [activeId, setActiveId] = useState<number | null>(null);
  /** One sound state for the whole feed. Sound is ON by default; when the
   * browser refuses un-muted autoplay (fresh page, no gesture yet) the slide
   * falls back to muted playback and restores sound on the first tap. */
  const [muted, setMuted] = useState(false);

  const seenRef = useRef<Set<number>>(new Set());
  const loadingMoreRef = useRef(false);

  /** "For you" (the unseen feed) vs "Saved" — the promise behind the bookmark. */
  const [tab, setTab] = useState<"feed" | "saved">("feed");
  const [savedReels, setSavedReels] = useState<Reel[] | null>(null);

  /** The "suggest an Instagram account" bottom sheet. */
  const [suggestOpen, setSuggestOpen] = useState(false);

  // Per-language feed. Mixing German and English in one scroll reads as
  // noise, so a multi-language learner watches one language at a time and
  // switches — by chip, or by swiping sideways (the vertical axis is taken).
  const feedLangs = user?.learning_languages ?? [];
  const multiLang = feedLangs.length > 1;
  const [lang, setLang] = useState<string>(() => {
    const stored = localStorage.getItem(LANG_KEY);
    if (stored && feedLangs.includes(stored)) return stored;
    return feedLangs[0] ?? "";
  });
  const [langHint, setLangHint] = useState(
    () => multiLang && !localStorage.getItem(LANG_HINT_KEY),
  );

  // The language question, shown in place of the feed when we've never asked.
  const [learning, setLearning] = useState<string[]>(user?.learning_languages ?? []);
  const [known, setKnown] = useState<string[]>(user?.known_languages ?? []);
  const [savingPrefs, setSavingPrefs] = useState(false);

  const load = useCallback(async (offset = 0, langOverride?: string) => {
    try {
      const wanted = langOverride ?? lang;
      // Always sent when known. Deciding client-side ("only narrow when
      // multi-language") read a stale closure right after the language gate —
      // savePrefs still held multiLang=false, requested the mixed feed, and
      // it only fixed itself on the next mount. The server validates against
      // the user's real languages anyway; for single-language users the
      // narrowed feed and the full feed are the same thing.
      const data = await fetchReels({ offset, lang: wanted || undefined });
      setNeedsPrefs(data.needs_language_prefs);
      setCaughtUp(!!data.caught_up);
      setNextOffset(data.next_offset ?? null);
      setReels((prev) => (offset === 0 ? data.results : [...prev, ...data.results]));
      if (data.needs_language_prefs && data.suggested_known_languages?.length) {
        setKnown((prev) => (prev.length ? prev : data.suggested_known_languages!));
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setLoading(false);
      loadingMoreRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, lang]);

  useEffect(() => {
    void load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function switchLang(next: string) {
    if (next === lang || !feedLangs.includes(next)) return;
    setLang(next);
    localStorage.setItem(LANG_KEY, next);
    if (langHint) {
      // They've switched once — the hint has done its job.
      setLangHint(false);
      localStorage.setItem(LANG_HINT_KEY, "1");
    }
    setActiveId(null);
    setReels([]);
    setLoading(true);
    void load(0, next);
  }

  /** Sideways swipe on the feed cycles languages; vertical stays with snap
   * scrolling. Direction-agnostic on purpose — with two languages either way
   * toggles, and in an RTL UI "next" has no obvious side. */
  const touchRef = useRef<{ x: number; y: number } | null>(null);
  function onFeedTouchStart(e: React.TouchEvent) {
    const t0 = e.touches[0];
    touchRef.current = { x: t0.clientX, y: t0.clientY };
  }
  function onFeedTouchEnd(e: React.TouchEvent) {
    const start = touchRef.current;
    touchRef.current = null;
    if (!start || !multiLang || tab !== "feed") return;
    const dx = e.changedTouches[0].clientX - start.x;
    const dy = e.changedTouches[0].clientY - start.y;
    if (Math.abs(dx) < 60 || Math.abs(dx) < 1.5 * Math.abs(dy)) return;
    const i = feedLangs.indexOf(lang);
    const next =
      dx < 0
        ? feedLangs[(i + 1) % feedLangs.length]
        : feedLangs[(i - 1 + feedLangs.length) % feedLangs.length];
    switchLang(next);
  }

  function onReelActive(reel: Reel) {
    setActiveId(reel.id);
    if (!seenRef.current.has(reel.id)) {
      seenRef.current.add(reel.id);
      void markReelSeen(reel.id).catch(() => {});
    }
  }

  function onEndReached() {
    if (nextOffset === null || loadingMoreRef.current) return;
    loadingMoreRef.current = true;
    void load(nextOffset);
  }

  async function savePrefs() {
    setSavingPrefs(true);
    try {
      await updateMe({ learning_languages: learning, known_languages: known });
      await refreshUser();
      setLoading(true);
      // Land on a definite language so the chips and the feed agree from the
      // first frame, even when they just picked several.
      const first = learning[0] ?? "";
      setLang(first);
      // The mount-time hint check ran while this user had no languages yet;
      // re-check now that they've just picked several.
      if (learning.length > 1 && !localStorage.getItem(LANG_HINT_KEY)) setLangHint(true);
      await load(0, first);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setSavingPrefs(false);
    }
  }

  function switchTab(next: "feed" | "saved") {
    if (next === tab) return;
    setTab(next);
    setActiveId(null);
    // Re-fetched on every entry: saves happen in the other tab, and a stale
    // list here reads as a lost bookmark.
    if (next === "saved") {
      setSavedReels(null);
      fetchSavedReels()
        .then((d) => setSavedReels(d.results))
        .catch(() => setSavedReels([]));
    }
  }

  async function onSave(reel: Reel) {
    // Optimistic, in both lists: the toggle should feel instant, and a failed
    // save is recoverable by tapping again. An unsaved reel stays in the Saved
    // list until the next visit so a mis-tap is one tap to undo.
    const flip = (list: Reel[]) =>
      list.map((r) => (r.id === reel.id ? { ...r, saved: !r.saved } : r));
    const revert = (list: Reel[]) =>
      list.map((r) => (r.id === reel.id ? { ...r, saved: reel.saved } : r));
    setReels(flip);
    setSavedReels((prev) => (prev ? flip(prev) : prev));
    try {
      await toggleReelSaved(reel.id);
    } catch {
      setReels(revert);
      setSavedReels((prev) => (prev ? revert(prev) : prev));
    }
  }

  if (loading) {
    return (
      <div className="reels-plain">
        <p className="muted">{t("common.loading")}</p>
      </div>
    );
  }

  if (needsPrefs) {
    return (
      <div className="reels-plain">
        <section className="reels-gate">
          <h1 className="page__title">{t("languages.needPrefsTitle")}</h1>
          <p className="muted">{t("languages.needPrefsLede")}</p>
          <LanguagePicker
            learning={learning}
            known={known}
            onChange={(next) => {
              setLearning(next.learning);
              setKnown(next.known);
            }}
          />
          <button
            className="btn btn--primary"
            disabled={!learning.length || savingPrefs}
            onClick={() => void savePrefs()}
          >
            {savingPrefs ? t("common.saving") : t("languages.save")}
          </button>
          {error && <p className="error">{error}</p>}
        </section>
      </div>
    );
  }

  // Single-language users get the plain empty page; multi-language users keep
  // the stage — the language chips must stay reachable when one feed is empty,
  // or an empty language becomes a dead end.
  if (!reels.length && !multiLang) {
    return (
      <div className="reels-plain">
        {error && <p className="error">{error}</p>}
        <p className="muted">{t("reels.empty")}</p>
      </div>
    );
  }

  const shown = tab === "feed" ? reels : savedReels ?? [];

  return (
    <div className="reels-stage">
      <div className="reels-tabs" role="tablist">
        <button
          className={`reels-tabs__tab${tab === "feed" ? " reels-tabs__tab--on" : ""}`}
          role="tab"
          aria-selected={tab === "feed"}
          onClick={() => switchTab("feed")}
        >
          {t("reels.forYou")}
        </button>
        <button
          className={`reels-tabs__tab${tab === "saved" ? " reels-tabs__tab--on" : ""}`}
          role="tab"
          aria-selected={tab === "saved"}
          onClick={() => switchTab("saved")}
        >
          {t("reels.savedTab")}
        </button>
        <button
          className="reels-tabs__tab reels-tabs__tab--plus"
          aria-label={t("reels.suggestTitle")}
          title={t("reels.suggestTitle")}
          onClick={() => setSuggestOpen(true)}
        >
          +
        </button>
      </div>

      {suggestOpen && <SuggestSheet onClose={() => setSuggestOpen(false)} />}

      {multiLang && tab === "feed" && (
        <div className="reels-langs" role="tablist" aria-label={t("reels.language")}>
          {feedLangs.map((code) => (
            <button
              key={code}
              className={`reels-langs__chip${code === lang ? " reels-langs__chip--on" : ""}`}
              role="tab"
              aria-selected={code === lang}
              onClick={() => switchLang(code)}
            >
              {languageEndonym(code)}
            </button>
          ))}
        </div>
      )}

      {langHint && tab === "feed" && (
        <p className="reels-feed__pill reels-feed__pill--hint">{t("reels.swipeHint")}</p>
      )}
      {tab === "feed" && caughtUp && !langHint && (
        <p className="reels-feed__pill">{t("reels.caughtUp")}</p>
      )}
      {error && <p className="reels-feed__pill reels-feed__pill--error">{error}</p>}

      {tab === "saved" && savedReels !== null && savedReels.length === 0 ? (
        <p className="reels-stage__empty">{t("reels.savedEmpty")}</p>
      ) : tab === "feed" && !shown.length ? (
        <p className="reels-stage__empty">{t("reels.emptyLang")}</p>
      ) : (
        <div
          className="reels-feed"
          onTouchStart={onFeedTouchStart}
          onTouchEnd={onFeedTouchEnd}
        >
          {shown.map((reel) => (
            <ReelSlide
              // Tab-scoped keys: the same reel can appear in both lists, and
              // reusing its mounted state across tabs would carry playback over.
              key={`${tab}-${reel.id}`}
              reel={reel}
              active={activeId === reel.id}
              muted={muted}
              onActive={() => onReelActive(reel)}
              onSetMuted={setMuted}
              onSave={() => void onSave(reel)}
            />
          ))}

          {tab === "feed" && nextOffset !== null && <EndSentinel onReach={onEndReached} />}
        </div>
      )}
    </div>
  );
}

/** Fires once each time it scrolls into view — the feed's "load more". */
function EndSentinel({ onReach }: { onReach: () => void }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const onReachRef = useRef(onReach);
  onReachRef.current = onReach;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) onReachRef.current();
      },
      // Start fetching one screen early so the scroll never hits a wall.
      { rootMargin: "100% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Invisible: snap scrolling means the user never actually sees the tail,
  // the early rootMargin fetch keeps the next page ready before they arrive.
  return <div ref={ref} className="reels-feed__more" aria-hidden />;
}

/** Bottom sheet: "suggest an Instagram account". The suggester picks the
 * languages — they know what the channel teaches better than a reviewer
 * guessing later — and staff approve it into a real source in the admin. */
function SuggestSheet({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [target, setTarget] = useState("de");
  const [base, setBase] = useState("");
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "busy" }
    | { kind: "done"; status: "ok" | "exists" | "pending" }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  function submit() {
    const handle = username.trim().replace(/^@/, "");
    if (!handle || state.kind === "busy") return;
    setState({ kind: "busy" });
    suggestReelSource({ username: handle, target_language: target, base_language: base })
      .then((r) => setState({ kind: "done", status: r.status }))
      .catch((e) =>
        setState({
          kind: "error",
          message: e instanceof Error && e.message ? e.message : t("common.error"),
        }),
      );
  }

  const doneMessage =
    state.kind === "done"
      ? {
          ok: t("reels.suggestThanks"),
          exists: t("reels.suggestExists"),
          pending: t("reels.suggestPending"),
        }[state.status]
      : null;

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={t("reels.suggestTitle")}>
      <button className="sheet__backdrop" aria-label={t("common.close")} onClick={onClose} />
      <div className="sheet__panel">
        <h2 className="sheet__title">{t("reels.suggestTitle")}</h2>

        {doneMessage ? (
          <>
            <p className="sheet__done">{doneMessage}</p>
            <button className="btn btn--primary" onClick={onClose}>
              {t("common.close")}
            </button>
          </>
        ) : (
          <>
            <p className="muted sheet__lede">{t("reels.suggestLede")}</p>
            <label className="sheet__label">
              {t("reels.suggestUsername")}
              <input
                className="sheet__input"
                dir="ltr"
                placeholder="@username"
                value={username}
                autoFocus
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label className="sheet__label">
              {t("reels.suggestTeaches")}
              <select
                className="sheet__input"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.endonym}
                  </option>
                ))}
              </select>
            </label>
            <label className="sheet__label">
              {t("reels.suggestBase")}
              <select
                className="sheet__input"
                value={base}
                onChange={(e) => setBase(e.target.value)}
              >
                <option value="">{t("reels.suggestImmersive")}</option>
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.endonym}
                  </option>
                ))}
              </select>
            </label>
            {state.kind === "error" && <p className="error">{state.message}</p>}
            <div className="sheet__actions">
              <button className="btn" onClick={onClose}>
                {t("common.cancel")}
              </button>
              <button
                className="btn btn--primary"
                disabled={!username.trim() || state.kind === "busy"}
                onClick={submit}
              >
                {state.kind === "busy" ? t("common.saving") : t("reels.suggestSubmit")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ReelSlide({
  reel,
  active,
  muted,
  onActive,
  onSetMuted,
  onSave,
}: {
  reel: Reel;
  active: boolean;
  muted: boolean;
  onActive: () => void;
  onSetMuted: (muted: boolean) => void;
  onSave: () => void;
}) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const onActiveRef = useRef(onActive);
  onActiveRef.current = onActive;

  // Driven by the video's own events, not by our clicks: `playing` fires only
  // once real frames render, which is exactly when the placeholder may go.
  const [paused, setPaused] = useState(true);
  const [buffering, setBuffering] = useState(false);
  /** The user tapped pause; don't fight them when the observer re-fires. */
  const userPausedRef = useRef(false);
  /** Sound is on globally but the browser refused un-muted autoplay, so this
   * slide is playing muted until a tap (a real gesture) restores sound. */
  const [autoMuted, setAutoMuted] = useState(false);
  const effectiveMuted = muted || autoMuted;

  /** "Make cards": idle → busy → the deck's id (button becomes an open-deck
   * link) or an error message. */
  const [cardsState, setCardsState] = useState<
    { kind: "idle" } | { kind: "busy" } | { kind: "done"; deck: number } | { kind: "error"; message: string }
  >({ kind: "idle" });

  function onMakeCards() {
    if (cardsState.kind === "busy" || cardsState.kind === "done") return;
    setCardsState({ kind: "busy" });
    makeCardsFromReel(reel.id)
      .then((r) => setCardsState({ kind: "done", deck: r.deck }))
      .catch((e) =>
        setCardsState({
          kind: "error",
          message: e instanceof Error && e.message ? e.message : t("reels.makeCardsFailed"),
        }),
      );
  }

  // Overlay chrome (caption, rail, tab bar). Visible while paused; once
  // playback starts it stays for a beat, then gets out of the way.
  const [chrome, setChrome] = useState(true);
  const hideTimer = useRef<number | null>(null);
  const clearHide = () => {
    if (hideTimer.current !== null) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
  };
  const scheduleHide = (ms: number) => {
    clearHide();
    hideTimer.current = window.setTimeout(() => setChrome(false), ms);
  };
  useEffect(() => clearHide, []);

  // The tab bar lives in the shell, outside this page — it fades via a body
  // class that only the active, chrome-less slide holds.
  useEffect(() => {
    if (active && !chrome) {
      document.body.classList.add("reels-immersive");
      return () => document.body.classList.remove("reels-immersive");
    }
  }, [active, chrome]);

  // The feed watches which slide owns the viewport.
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting && e.intersectionRatio >= 0.6) onActiveRef.current();
        }
      },
      { threshold: [0.6] },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Play when this slide owns the screen, stop the moment it doesn't. The
  // muted attribute is set imperatively too: the play() call and the flag
  // must change together or mobile Safari rejects the play.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = effectiveMuted;
    if (active) {
      if (!userPausedRef.current && v.paused) {
        v.play().catch(() => {
          // Un-muted autoplay is refused until the page has seen a gesture;
          // muted playback is always allowed. Start silent rather than
          // frozen — the first tap on the slide brings the sound back.
          if (!v.muted) {
            v.muted = true;
            setAutoMuted(true);
            void v.play().catch(() => setBuffering(false));
          } else {
            setBuffering(false);
          }
        });
      }
    } else {
      if (!v.paused) v.pause();
      userPausedRef.current = false;
      setAutoMuted(false);
    }
  }, [active, effectiveMuted]);

  /** Every tap is a real gesture — the one thing the autoplay fallback has
   * been waiting for. */
  function restoreSoundIfAutoMuted() {
    const v = videoRef.current;
    if (autoMuted && v) {
      v.muted = muted;
      setAutoMuted(false);
    }
  }

  // Tap logic, Instagram-style. Chrome hidden: first tap only brings the
  // overlays back. Chrome visible: tap toggles play/pause. No native
  // controls — on mobile those swallow the first tap to reveal themselves.
  function onTap() {
    const v = videoRef.current;
    if (!v) return;
    restoreSoundIfAutoMuted();
    if (v.paused) {
      userPausedRef.current = false;
      void v.play().catch(() => setBuffering(false));
    } else if (!chrome) {
      setChrome(true);
      // Longer than the after-play beat: leave room for the second tap.
      scheduleHide(3000);
    } else {
      userPausedRef.current = true;
      v.pause();
    }
  }

  return (
    <section ref={rootRef} className={`reelview${chrome ? "" : " reelview--immersive"}`}>
      <div className="reelview__frame">
        <video
          ref={videoRef}
          className="reelview__video"
          src={reel.video_url ?? undefined}
          poster={reel.poster_url ?? undefined}
          playsInline
          loop
          // Only the on-screen reel downloads — see the note at the top.
          preload="none"
          onPlay={(e) => {
            setPaused(false);
            // preload="none" means the first play starts with a download —
            // spinner until `playing` says frames are up. A resume of an
            // already-buffered video skips it, so the badge doesn't flash.
            if (e.currentTarget.readyState < 3) setBuffering(true);
          }}
          onPlaying={() => {
            setBuffering(false);
            // One clear second of context, then the reel gets the screen.
            scheduleHide(1000);
          }}
          onWaiting={() => setBuffering(true)}
          onPause={() => {
            setPaused(true);
            setBuffering(false);
            clearHide();
            setChrome(true);
          }}
        />

        <button
          className="reelview__tap"
          aria-label={paused ? t("reels.play") : t("reels.pause")}
          onClick={onTap}
        >
          {buffering ? (
            <span className="reelview__badge" aria-hidden="true">
              <span className="reelview__spinner" />
            </span>
          ) : paused ? (
            <span className="reelview__badge" aria-hidden="true">
              ▶
            </span>
          ) : null}
        </button>

        {/* Action rail, Instagram-style: icon-only, stacked on the trailing
            edge; what each does is in the aria-label. */}
        <div className="reelview__rail">
          <button
            className={`reelview__action${reel.saved ? " reelview__action--on" : ""}`}
            aria-pressed={reel.saved}
            aria-label={reel.saved ? t("reels.saved") : t("reels.save")}
            onClick={() => {
              if (!paused) scheduleHide(3000);
              onSave();
            }}
          >
            <IconBookmark filled={reel.saved} />
          </button>
          <button
            className="reelview__action"
            aria-label={effectiveMuted ? t("reels.unmute") : t("reels.mute")}
            onClick={() => {
              const v = videoRef.current;
              const next = !effectiveMuted;
              setAutoMuted(false);
              if (v) v.muted = next;
              onSetMuted(next);
              if (!paused) scheduleHide(3000);
            }}
          >
            <IconSound muted={effectiveMuted} />
          </button>
        </div>

        {/* Meta over the bottom of the video, behind the tab bar clearance. */}
        <div className="reelview__meta">
          <div className="reelview__who">
            <span className="reelview__source">
              {reel.is_ours ? t("reels.ours") : `@${reel.source_username}`}
            </span>
            <span className="reelview__teaches">{reel.teaches}</span>
          </div>
          {(reel.title || reel.caption) && (
            <p className="reelview__caption">{reel.title || reel.caption}</p>
          )}
          {reel.make_cards && (
            <div className="reelview__cards">
              {cardsState.kind === "done" ? (
                <Link className="reelview__cardsbtn reelview__cardsbtn--done" to={`/app/decks/${cardsState.deck}`}>
                  {t("reels.openDeck")}
                </Link>
              ) : (
                <button
                  className="reelview__cardsbtn"
                  disabled={cardsState.kind === "busy"}
                  onClick={onMakeCards}
                >
                  {cardsState.kind === "busy" ? t("reels.makingCards") : t("reels.makeCards")}
                </button>
              )}
              {cardsState.kind === "error" && (
                <span className="reelview__cardserr">{cardsState.message}</span>
              )}
            </div>
          )}
          {/* Attribution stays even where the link isn't reachable — crediting
              the creator isn't conditional on our users being able to click. */}
          {reel.url && !reel.is_ours && (
            <a className="reelview__origin" href={reel.url} target="_blank" rel="noreferrer">
              {t("reels.original")}
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

function IconBookmark({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} aria-hidden>
      <path
        d="M6 4h12a1 1 0 011 1v16l-7-4.5L5 21V5a1 1 0 011-1z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconSound({ muted }: { muted: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 9v6h4l5 4V5L8 9H4z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {muted ? (
        <path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      ) : (
        <path
          d="M16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

