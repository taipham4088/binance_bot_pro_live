import React from "react";
import "./intent_client";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./dashboard.css";
import "./theme/theme.css";

const root = ReactDOM.createRoot(
  document.getElementById("root") as HTMLElement
);

root.render(
  <App />
);