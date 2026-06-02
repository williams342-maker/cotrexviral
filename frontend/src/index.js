import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { installBackendUrlGuard } from "@/lib/backendUrlGuard";

// Run before React mounts so the safety net is live for the very first
// API call. Pure DOM/axios — does NOT depend on React.
installBackendUrlGuard();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
