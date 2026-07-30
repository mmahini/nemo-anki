import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initPwaUpdates } from "./pwa";
import "./styles.css";
import "./i18n";

initPwaUpdates();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
