import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { cdpPage, initCdpPixel } from "./lib/cdp-pixel";
import { captureReferralCode } from "./lib/referral";
import { AuthProvider } from "./auth/AuthContext";
import LandingPage from "./components/LandingPage";
import ProtectedRoute from "./pages/ProtectedRoute";
import SignIn from "./pages/SignIn";
import Verify from "./pages/Verify";
import Welcome from "./pages/Welcome";
import AppShell from "./pages/AppShell";
import Home from "./pages/Home";
import Decks from "./pages/Decks";
import Stats from "./pages/Stats";
import DeckCards from "./pages/DeckCards";
import AddCard from "./pages/AddCard";
import ImportPage from "./pages/Import";
import Books from "./pages/Books";
import BookPage from "./pages/BookPage";
import Study from "./pages/Study";
import StudyCard from "./pages/StudyCard";
import PlacementTest from "./pages/PlacementTest";
import PlacementTestRun from "./pages/PlacementTestRun";
import Practice from "./pages/Practice";
import Support from "./pages/Support";
import Subscribe from "./pages/Subscribe";
import Classroom from "./pages/Classroom";
import BackendStatus from "./components/BackendStatus";
import UpdateToast from "./components/UpdateToast";
import SpeechHelp from "./components/SpeechHelp";

// Emit a Wiser CDP pageview on every route change (no-op unless the pixel is configured).
function CdpRouteTracker() {
  const location = useLocation();
  // Start engagement-time tracking + the page_leave beacon once (CDP-9.1).
  useEffect(() => {
    initCdpPixel();
  }, []);
  useEffect(() => {
    cdpPage({ path: location.pathname });
  }, [location.pathname]);
  return null;
}

export default function App() {
  // Stash an invite link's ?ref= code before any routing; it's redeemed at
  // verify-otp (see lib/referral.ts).
  useEffect(() => {
    captureReferralCode();
  }, []);

  return (
    <AuthProvider>
      <BrowserRouter>
        <CdpRouteTracker />
        <BackendStatus />
        <UpdateToast />
        <SpeechHelp />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth/sign-in" element={<SignIn />} />
          <Route path="/auth/verify" element={<Verify />} />
          <Route element={<ProtectedRoute />}>
            {/* First-run walkthrough: full-screen, no nav — there's nothing to
                navigate to until it's done. */}
            <Route path="/welcome" element={<Welcome />} />
            {/* Study runs full-screen, outside the shell chrome. */}
            <Route path="/app/study/:deckId" element={<Study />} />
            <Route path="/app/study/card/:cardId" element={<StudyCard />} />
            {/* The quiz itself is full-screen too; its setup page lives in the
                shell as a main page (see PlacementTest). */}
            <Route path="/app/placement-test/run" element={<PlacementTestRun />} />
            <Route element={<AppShell />}>
              <Route path="/app" element={<Home />} />
              <Route path="/app/placement-test" element={<PlacementTest />} />
              <Route path="/app/decks" element={<Decks />} />
              <Route path="/app/stats" element={<Stats />} />
              <Route path="/app/decks/:deckId" element={<DeckCards />} />
              <Route path="/app/decks/:deckId/add" element={<AddCard />} />
              <Route path="/app/books" element={<Books />} />
              <Route path="/app/books/:bookId" element={<BookPage />} />
              <Route path="/app/import" element={<ImportPage />} />
              <Route path="/app/practice" element={<Practice />} />
              <Route path="/app/practice/:tab" element={<Practice />} />
              {/* Writing and Conversation merged into Practice. Keep the old
                  paths working — they're bookmarked, and an installed PWA can
                  hold a stale link for a while. */}
              <Route path="/app/write" element={<Navigate to="/app/practice/write" replace />} />
              <Route
                path="/app/conversation"
                element={<Navigate to="/app/practice/speak" replace />}
              />
              <Route path="/app/support" element={<Support />} />
              <Route path="/app/subscribe" element={<Subscribe />} />
              <Route path="/app/classroom" element={<Classroom />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
