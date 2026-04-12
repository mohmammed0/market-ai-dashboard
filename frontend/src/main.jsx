import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./design-system.css";
import "./styles.css";

document.documentElement.lang = "ar";
document.documentElement.dir = "rtl";
document.body.dir = "rtl";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
