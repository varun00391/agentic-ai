import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, ApiError } from "./api";
import { useAuth } from "./auth";
import { AuthFrame, Button, Field, TextInput, TextLink } from "./ui";

export function SignupPage() {
  const { token, setSession } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
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
      const payload = await api.signup({
        email,
        password,
        display_name: displayName,
        organization_name: organizationName,
      });
      setSession(payload);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create account");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      kicker="Get started"
      title="Open a workspace"
      subtitle="You become the owner. Invite others later through the API roles."
      footer={
        <>
          Already have access? <TextLink to="/login">Sign in</TextLink>
        </>
      }
    >
      <form className="space-y-4" onSubmit={onSubmit}>
        <Field label="Your name">
          <TextInput
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
          />
        </Field>
        <Field label="Organization">
          <TextInput
            value={organizationName}
            onChange={(event) => setOrganizationName(event.target.value)}
            required
          />
        </Field>
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
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </Field>
        {error ? <p className="text-sm text-rose-800">{error}</p> : null}
        <Button className="mt-2 w-full" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create workspace"}
        </Button>
      </form>
    </AuthFrame>
  );
}
