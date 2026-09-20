import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import type { Organization, TokenResponse } from "./types";

const TOKEN_KEY = "expense-v2-token";
const ORG_KEY = "expense-v2-org";

type AuthState = {
  token: string | null;
  userId: string | null;
  email: string | null;
  displayName: string | null;
  organizations: Organization[];
  currentOrg: Organization | null;
  ready: boolean;
};

type AuthContextValue = AuthState & {
  setSession: (payload: TokenResponse) => void;
  selectOrg: (organizationId: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: localStorage.getItem(TOKEN_KEY),
    userId: null,
    email: null,
    displayName: null,
    organizations: [],
    currentOrg: null,
    ready: false,
  });

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setState((current) => ({ ...current, ready: true, token: null }));
      return;
    }
    api
      .me(token)
      .then((me) => {
        const savedOrg = localStorage.getItem(ORG_KEY);
        const currentOrg =
          me.organizations.find((org) => org.id === savedOrg) ??
          me.organizations[0] ??
          null;
        if (currentOrg) {
          localStorage.setItem(ORG_KEY, currentOrg.id);
        }
        setState({
          token,
          userId: me.user_id,
          email: me.email,
          displayName: me.display_name,
          organizations: me.organizations,
          currentOrg,
          ready: true,
        });
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(ORG_KEY);
        setState({
          token: null,
          userId: null,
          email: null,
          displayName: null,
          organizations: [],
          currentOrg: null,
          ready: true,
        });
      });
  }, []);

  const setSession = useCallback((payload: TokenResponse) => {
    localStorage.setItem(TOKEN_KEY, payload.access_token);
    const currentOrg = payload.organizations[0] ?? null;
    if (currentOrg) {
      localStorage.setItem(ORG_KEY, currentOrg.id);
    }
    setState({
      token: payload.access_token,
      userId: payload.user_id,
      email: payload.email,
      displayName: payload.display_name,
      organizations: payload.organizations,
      currentOrg,
      ready: true,
    });
  }, []);

  const selectOrg = useCallback((organizationId: string) => {
    setState((current) => {
      const next = current.organizations.find((org) => org.id === organizationId) ?? null;
      if (next) {
        localStorage.setItem(ORG_KEY, next.id);
      }
      return { ...current, currentOrg: next };
    });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ORG_KEY);
    setState({
      token: null,
      userId: null,
      email: null,
      displayName: null,
      organizations: [],
      currentOrg: null,
      ready: true,
    });
  }, []);

  const value = useMemo(
    () => ({ ...state, setSession, selectOrg, logout }),
    [state, setSession, selectOrg, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
