import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

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
import BackendStatus from "./components/BackendStatus";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
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
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
