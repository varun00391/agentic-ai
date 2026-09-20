import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./AppShell";
import { AuthProvider } from "./auth";
import { DashboardPage } from "./DashboardPage";
import { LoginPage } from "./LoginPage";
import { ProcessPage } from "./ProcessPage";
import { RequireAuth } from "./RequireAuth";
import { SettingsPage } from "./SettingsPage";
import { SignupPage } from "./SignupPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/process" element={<ProcessPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/process/:expenseId" element={<LegacyExpenseRedirect />} />
              <Route path="/expenses" element={<Navigate to="/process" replace />} />
              <Route path="/expenses/:expenseId" element={<LegacyExpenseRedirect />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

function LegacyExpenseRedirect() {
  const { expenseId } = useParams();
  return <Navigate to={`/process?view=${expenseId ?? ""}`} replace />;
}
