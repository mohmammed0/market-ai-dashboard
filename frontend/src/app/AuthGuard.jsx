import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { checkAuthStatus, isAuthenticated } from "../api/auth";
import PageSkeleton from "./PageSkeleton";

export default function AuthGuard({ children }) {
  const [authEnabled, setAuthEnabled] = useState(true);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    let active = true;
    checkAuthStatus()
      .then((status) => {
        if (!active) return;
        setAuthEnabled(status?.auth_enabled !== false);
      })
      .catch(() => {
        if (!active) return;
        setAuthEnabled(true);
      })
      .finally(() => {
        if (active) setCheckingAuth(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (checkingAuth) {
    return <PageSkeleton />;
  }

  if (authEnabled && !isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
