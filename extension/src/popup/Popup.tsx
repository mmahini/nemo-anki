import { useEffect, useState, type FormEvent } from "react";
import { ApiError, AuthRequiredError, fetchMe, requestOtp, signOut, verifyOtp } from "../lib/api";
import { clearPendingOtp, loadPendingOtp, loadStoredAuth, savePendingOtp } from "../lib/auth";
import type { AuthUser } from "../lib/types";

type Step = "loading" | "email" | "code" | "signed-in";

export function Popup() {
  const [step, setStep] = useState<Step>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [email, setEmail] = useState("");
  const [otpId, setOtpId] = useState("");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      const stored = await loadStoredAuth();
      if (stored) {
        // Validate rather than trust the cached blob outright — request()
        // already retries once via the refresh token on a 401, so this
        // either confirms the session or tells us the refresh token is
        // actually dead (AuthRequiredError), not just that one call failed.
        try {
          const fresh = await fetchMe();
          setUser(fresh);
          setStep("signed-in");
        } catch (err) {
          if (err instanceof AuthRequiredError) {
            setStep("email");
          } else {
            // Network/server hiccup — don't sign a user out over a
            // transient failure, just trust the cached profile for now.
            setUser(stored.user);
            setStep("signed-in");
          }
        }
        return;
      }

      // Not signed in — resume an in-progress OTP login if the popup was
      // closed and reopened mid-flow (Chrome unloads it on every outside
      // click) instead of asking for the email again.
      const pending = await loadPendingOtp();
      if (pending) {
        setEmail(pending.email);
        setOtpId(pending.otpId);
        setDevCode(pending.devCode ?? "");
        setStep("code");
        return;
      }

      setStep("email");
    })();
  }, []);

  async function handleRequestOtp(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const trimmedEmail = email.trim();
      const res = await requestOtp(trimmedEmail);
      setOtpId(res.otp_id);
      setDevCode(res.dev_code ?? "");
      await savePendingOtp({ email: trimmedEmail, otpId: res.otp_id, devCode: res.dev_code });
      setStep("code");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send the code — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleVerifyOtp(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const signedInUser = await verifyOtp(otpId, code.trim());
      await clearPendingOtp();
      setUser(signedInUser);
      setStep("signed-in");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Incorrect code — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSignOut() {
    await signOut();
    setUser(null);
    setEmail("");
    setCode("");
    setStep("email");
  }

  function handleStartVoice() {
    // Same window size background.ts uses for a text capture — the proposal
    // window handles both "capture=<id>" (text) and "mode=voice" the same way.
    void chrome.windows.create({
      url: chrome.runtime.getURL("proposal.html?mode=voice"),
      type: "popup",
      width: 420,
      height: 600,
    });
    window.close();
  }

  if (step === "loading") {
    return (
      <main className="popup">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  if (step === "signed-in" && user) {
    return (
      <main className="popup">
        <h1>Nemo Anki</h1>
        <p className="muted">Signed in as {user.email}</p>
        <p>
          Select text on any page, then right-click and choose <strong>Add to Nemo
          Anki</strong> (or use the keyboard shortcut — see
          chrome://extensions/shortcuts) to turn it into a flashcard.
        </p>
        <button type="button" onClick={handleStartVoice}>
          🎤 Record voice
        </button>
        <button type="button" className="secondary" onClick={() => void handleSignOut()}>
          Sign out
        </button>
      </main>
    );
  }

  if (step === "code") {
    return (
      <main className="popup">
        <h1>Enter your code</h1>
        <p className="muted">We sent a 5-digit code to {email}.</p>
        {devCode && <p className="muted">Dev code: {devCode}</p>}
        <form onSubmit={(e) => void handleVerifyOtp(e)}>
          <input
            type="text"
            inputMode="numeric"
            placeholder="12345"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoFocus
            required
          />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Verifying…" : "Verify"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="popup">
      <h1>Sign in to Nemo Anki</h1>
      <form onSubmit={(e) => void handleRequestOtp(e)}>
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoFocus
          required
        />
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Sending…" : "Send code"}
        </button>
      </form>
    </main>
  );
}
