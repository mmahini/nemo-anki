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
import Study from "./pages/Study";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth/sign-in" element={<SignIn />} />
          <Route path="/auth/verify" element={<Verify />} />
          <Route element={<ProtectedRoute />}>
            {/* Study runs full-screen, outside the shell chrome. */}
            <Route path="/app/study/:deckId" element={<Study />} />
            <Route element={<AppShell />}>
              <Route path="/app" element={<Decks />} />
              <Route path="/app/decks/:deckId" element={<DeckCards />} />
              <Route path="/app/decks/:deckId/add" element={<AddCard />} />
              <Route path="/app/books" element={<Books />} />
              <Route path="/app/import" element={<ImportPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
