import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  fetchReels,
  markReelSeen,
  toggleReelSaved,
  updateMe,
  type Reel,
} from "../auth/api";
import { useAuth } from "../auth/AuthContext";
import LanguagePicker from "../components/LanguagePicker";

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
  /** One sound state for the whole feed, like Instagram: unmute once, every
   * following reel plays with sound. */
  const [muted, setMuted] = useState(true);

  const seenRef = useRef<Set<number>>(new Set());
  const loadingMoreRef = useRef(false);

  // The language question, shown in place of the feed when we've never asked.
  const [learning, setLearning] = useState<string[]>(user?.learning_languages ?? []);
  const [known, setKnown] = useState<string[]>(user?.known_languages ?? []);
  const [savingPrefs, setSavingPrefs] = useState(false);

  const load = useCallback(async (offset = 0) => {
    try {
      const data = await fetchReels({ offset });
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
  }, [t]);

  useEffect(() => {
    void load(0);
  }, [load]);

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
      await load(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setSavingPrefs(false);
    }
  }

  async function onSave(reel: Reel) {
    // Optimistic: the toggle should feel instant, and a failed save is
    // recoverable by tapping again.
    setReels((prev) =>
      prev.map((r) => (r.id === reel.id ? { ...r, saved: !r.saved } : r)),
    );
    try {
      await toggleReelSaved(reel.id);
    } catch {
      setReels((prev) =>
        prev.map((r) => (r.id === reel.id ? { ...r, saved: reel.saved } : r)),
      );
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

  if (!reels.length) {
    return (
      <div className="reels-plain">
        {error && <p className="error">{error}</p>}
        <p className="muted">{t("reels.empty")}</p>
      </div>
    );
  }

  return (
    <div className="reels-stage">
      {caughtUp && <p className="reels-feed__pill">{t("reels.caughtUp")}</p>}
      {error && <p className="reels-feed__pill reels-feed__pill--error">{error}</p>}

      <div className="reels-feed">
        {reels.map((reel) => (
          <ReelSlide
            key={reel.id}
            reel={reel}
            active={activeId === reel.id}
            muted={muted}
            onActive={() => onReelActive(reel)}
            onToggleMuted={() => setMuted((m) => !m)}
            onSave={() => void onSave(reel)}
          />
        ))}

        {nextOffset !== null && <EndSentinel onReach={onEndReached} />}
      </div>
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

function ReelSlide({
  reel,
  active,
  muted,
  onActive,
  onToggleMuted,
  onSave,
}: {
  reel: Reel;
  active: boolean;
  muted: boolean;
  onActive: () => void;
  onToggleMuted: () => void;
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
    v.muted = muted;
    if (active) {
      if (!userPausedRef.current && v.paused) {
        v.play().catch(() => {
          // Unmuted autoplay can be refused without a fresh gesture;
          // muted playback is always allowed. Degrade rather than freeze.
          if (!v.muted) {
            v.muted = true;
            void v.play().catch(() => setBuffering(false));
          } else {
            setBuffering(false);
          }
        });
      }
    } else {
      if (!v.paused) v.pause();
      userPausedRef.current = false;
    }
  }, [active, muted]);

  // One tap toggles play/pause. No native controls — on mobile those swallow
  // the first tap to reveal themselves, which forces a second one.
  function toggle() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      userPausedRef.current = false;
      void v.play().catch(() => setBuffering(false));
    } else {
      userPausedRef.current = true;
      v.pause();
    }
  }

  return (
    <section ref={rootRef} className="reelview">
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
          onPlaying={() => setBuffering(false)}
          onWaiting={() => setBuffering(true)}
          onPause={() => {
            setPaused(true);
            setBuffering(false);
          }}
        />

        <button
          className="reelview__tap"
          aria-label={paused ? t("reels.play") : t("reels.pause")}
          onClick={toggle}
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
            onClick={onSave}
          >
            <IconBookmark filled={reel.saved} />
          </button>
          <button
            className="reelview__action"
            aria-label={muted ? t("reels.unmute") : t("reels.mute")}
            onClick={onToggleMuted}
          >
            <IconSound muted={muted} />
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

