import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api, { TOKEN_KEY } from "../api/axios";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      if (!token) {
        setUser(null);
        setLoading(false);
        return;
      }
      try {
        const { data } = await api.get("/auth/me");
        if (!cancelled) setUser(data);
      } catch {
        if (!cancelled) logout();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    hydrate();
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  const login = useCallback(async (email, password) => {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);
    const { data } = await api.post("/auth/login", body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
    const me = await api.get("/auth/me", {
      headers: { Authorization: `Bearer ${data.access_token}` },
    });
    setUser(me.data);
    return me.data;
  }, []);

  const register = useCallback(async (email, password) => {
    await api.post("/auth/register", { email, password });
    return login(email, password);
  }, [login]);

  const value = useMemo(
    () => ({ user, token, loading, login, register, logout }),
    [user, token, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
