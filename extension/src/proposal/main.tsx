import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Proposal } from "./Proposal";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Proposal />
  </StrictMode>,
);
