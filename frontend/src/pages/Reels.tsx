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

/** Short videos from language-teaching accounts, plus our own.
 *
 * Playback is a plain <video> off our own CDN — no Instagram embed, which would
 * render an empty box for anyone behind the block that made us host the files
 * in the first place.
 *
 * `preload="none"` is load-bearing, not a micro-optimisation: at ~3 MB a reel,
 * letting a scroll preload the whole page would cost someone on mobile data a
 * fortune for videos they never played.
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
  const [playing, setPlaying] = useState<number | null>(null);

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
    }
  }, [t]);

  useEffect(() => {
    void load(0);
  }, [load]);

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

  if (loading) return <p className="muted">{t("common.loading")}</p>;

  if (needsPrefs) {
    return (
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
    );
  }

  return (
    <section className="reels">
      <h1 className="page__title">{t("nav.reels")}</h1>
      {caughtUp && <p className="muted reels__caughtup">{t("reels.caughtUp")}</p>}
      {error && <p className="error">{error}</p>}

      {!reels.length ? (
        <p className="muted">{t("reels.empty")}</p>
      ) : (
        <ul className="reels__list">
          {reels.map((reel) => (
            <ReelCard
              key={reel.id}
              reel={reel}
              playing={playing === reel.id}
              onPlay={() => {
                setPlaying(reel.id);
                void markReelSeen(reel.id).catch(() => {});
              }}
              onSave={() => void onSave(reel)}
            />
          ))}
        </ul>
      )}

      {nextOffset !== null && (
        <button className="btn" onClick={() => void load(nextOffset)}>
          {t("reels.more")}
        </button>
      )}
    </section>
  );
}

function ReelCard({
  reel,
  playing,
  onPlay,
  onSave,
}: {
  reel: Reel;
  playing: boolean;
  onPlay: () => void;
  onSave: () => void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLVideoElement | null>(null);

  return (
    <li className="reelcard">
      <div className="reelcard__media">
        <video
          ref={ref}
          className="reelcard__video"
          src={reel.video_url ?? undefined}
          poster={reel.poster_url ?? undefined}
          controls={playing}
          playsInline
          // Nothing downloads until the user asks for it — see the note above.
          preload="none"
          onPlay={onPlay}
        />
        {!playing && (
          <button
            className="reelcard__play"
            aria-label={t("reels.play")}
            onClick={() => {
              onPlay();
              void ref.current?.play();
            }}
          >
            ▶
          </button>
        )}
      </div>

      <div className="reelcard__body">
        <div className="reelcard__meta">
          <span className="reelcard__source">
            {reel.is_ours ? t("reels.ours") : `@${reel.source_username}`}
          </span>
          <span className="reelcard__teaches">{reel.teaches}</span>
        </div>
        {(reel.title || reel.caption) && (
          <p className="reelcard__caption">{reel.title || reel.caption}</p>
        )}
        <div className="reelcard__actions">
          <button
            className={`btn btn--small${reel.saved ? " btn--on" : ""}`}
            aria-pressed={reel.saved}
            onClick={onSave}
          >
            {reel.saved ? t("reels.saved") : t("reels.save")}
          </button>
          {/* Attribution stays even where the link isn't reachable — crediting
              the creator isn't conditional on our users being able to click. */}
          {reel.url && !reel.is_ours && (
            <a className="reelcard__origin" href={reel.url} target="_blank" rel="noreferrer">
              {t("reels.original")}
            </a>
          )}
        </div>
      </div>
    </li>
  );
}
