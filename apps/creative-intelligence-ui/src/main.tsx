import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import "@fontsource-variable/inter";
import "@/theme.css";
import { AuthProvider } from "@/auth/AuthProvider";
import { LocalePrefsSync, LocaleProvider } from "@/i18n";
import { router } from "@/app/router";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
createRoot(root).render(
  <StrictMode>
    <AuthProvider>
      <LocaleProvider>
        <LocalePrefsSync />
        <RouterProvider router={router} />
      </LocaleProvider>
    </AuthProvider>
  </StrictMode>,
);
