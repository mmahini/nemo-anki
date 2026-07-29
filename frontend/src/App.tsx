import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { cdpPage, initCdpPixel } from "./lib/cdp-pixel";
import { AuthProvider } from "./auth/AuthContext";
import LandingPage from "./components/LandingPage";
import ProtectedRoute from "./pages/ProtectedRoute";
import SignIn from "./pages/SignIn";
import Verify from "./pages/Verify";
import AppShell from "./pages/AppShell";
import Decks from "./pages/Decks";
import DeckCards from "./pages/DeckCards";
import AddCard from "./pages/AddCard";
import ImportPage from "./pages/Import";
import Books from "./pages/Books";
import BookPage from "./pages/BookPage";
import Study from "./pages/Study";
import StudyCard from "./pages/StudyCard";
import Writing from "./pages/Writing";
import Conversation from "./pages/Conversation";
import Subscribe from "./pages/Subscribe";
import BackendStatus from "./components/BackendStatus";

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
  return (
    <AuthProvider>
      <BrowserRouter>
        <CdpRouteTracker />
        <BackendStatus />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth/sign-in" element={<SignIn />} />
          <Route path="/auth/verify" element={<Verify />} />
          <Route element={<ProtectedRoute />}>
            {/* Study runs full-screen, outside the shell chrome. */}
            <Route path="/app/study/:deckId" element={<Study />} />
            <Route path="/app/study/card/:cardId" element={<StudyCard />} />
            <Route element={<AppShell />}>
              <Route path="/app" element={<Decks />} />
              <Route path="/app/decks/:deckId" element={<DeckCards />} />
              <Route path="/app/decks/:deckId/add" element={<AddCard />} />
              <Route path="/app/books" element={<Books />} />
              <Route path="/app/books/:bookId" element={<BookPage />} />
              <Route path="/app/import" element={<ImportPage />} />
              <Route path="/app/write" element={<Writing />} />
              <Route path="/app/conversation" element={<Conversation />} />
              <Route path="/app/subscribe" element={<Subscribe />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
