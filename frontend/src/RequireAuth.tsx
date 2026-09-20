import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./auth";

export function RequireAuth() {
  const { token, ready } = useAuth();
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted">
        Restoring session…
      </div>
    );
  }
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
