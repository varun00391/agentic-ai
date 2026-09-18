import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import { AuthFrame, Button, Field, TextInput, TextLink } from "./ui";

export function LoginPage() {
  const { token, setSession } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (token) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const payload = await api.login(email, password);
      setSession(payload);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      kicker="Expense capture"
      title="Welcome back"
      subtitle="Sign in to upload receipts and follow the agent as it posts expenses."
      footer={
        <>
          New organization? <TextLink to="/signup">Create an account</TextLink>
        </>
      }
    >
      <form className="space-y-4" onSubmit={onSubmit}>
        <Field label="Email">
          <TextInput
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </Field>
        <Field label="Password">
          <TextInput
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </Field>
        {error ? <p className="text-sm text-rose-800">{error}</p> : null}
        <Button className="mt-2 w-full" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Continue"}
        </Button>
      </form>
    </AuthFrame>
  );
}
