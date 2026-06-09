import { useEffect, useState } from "react";

/** Friendly banner shown while the free-tier backend wakes from sleep. Driven
 * by the "nemo:waking" window event emitted by the API layer during retries. */
export default function BackendStatus() {
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    const onWaking = (e: Event) => setWaking((e as CustomEvent).detail === true);
    window.addEventListener("nemo:waking", onWaking);
    return () => window.removeEventListener("nemo:waking", onWaking);
  }, []);

  if (!waking) return null;

  return (
    <div className="wakebanner" role="status" aria-live="polite">
      <span className="wakebanner__spinner" aria-hidden="true" />
      <span>
        Waking the server up… it's free hosting that naps after a while, so the first
        load can take 20–40 seconds. Hang tight — no need to refresh.
      </span>
    </div>
  );
}
