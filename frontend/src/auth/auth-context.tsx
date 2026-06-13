import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { apiClient, refreshTokens } from "@/lib/api-client";
import { tokenStore } from "@/lib/token-store";
import type { TokenPair, UserPublic } from "@/types";

export interface RegisterPayload {
  email: string;
  password: string;
  display_name: string;
}

interface AuthContextValue {
  user: UserPublic | null;
  isAuthenticated: boolean;
  isBootstrapping: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Store a ready-made token pair (e.g. magic-link callback) and fetch the user. */
  loginWithTokenPair: (pair: TokenPair) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<UserPublic>;
  logout: () => Promise<void>;
  /** Replace the cached user (e.g. after a settings update, spec 59). */
  applyUser: (user: UserPublic) => void;
  /** Re-fetch the current user from the server. */
  refreshUser: () => Promise<void>;
  /** Use a persisted refresh token to restore the session (auto-run on mount). */
  bootstrap: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  // Drop the user whenever tokens are cleared (e.g. a failed refresh-on-401).
  useEffect(() => {
    return tokenStore.subscribe(() => {
      if (!tokenStore.getAccessToken()) setUser(null);
    });
  }, []);

  // Use a persisted refresh token to obtain an access token + user. Exposed so
  // callers can re-run it imperatively; also auto-run once on mount below.
  const bootstrap = useCallback(async (): Promise<void> => {
    setIsBootstrapping(true);
    try {
      if (tokenStore.getRefreshToken()) {
        if (await refreshTokens()) {
          const me = await apiClient.get<UserPublic>("/api/v1/users/me");
          setUser(me);
        }
      }
    } catch {
      // Ignore: stay unauthenticated.
    } finally {
      setIsBootstrapping(false);
    }
  }, []);

  // On load, restore the session from a persisted refresh token.
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  const login = async (email: string, password: string): Promise<void> => {
    const pair = await apiClient.post<TokenPair>(
      "/api/v1/auth/login",
      { email, password },
      { auth: false },
    );
    tokenStore.setTokens({ access: pair.access_token, refresh: pair.refresh_token });
    const me = await apiClient.get<UserPublic>("/api/v1/users/me");
    setUser(me);
  };

  // Share the exact post-login path as `login`, but from an already-issued pair
  // (the magic-link callback, spec 104). No credentials are involved.
  const loginWithTokenPair = async (pair: TokenPair): Promise<void> => {
    tokenStore.setTokens({ access: pair.access_token, refresh: pair.refresh_token });
    const me = await apiClient.get<UserPublic>("/api/v1/users/me");
    setUser(me);
  };

  const register = (payload: RegisterPayload): Promise<UserPublic> =>
    apiClient.post<UserPublic>("/api/v1/auth/register", payload, { auth: false });

  const logout = async (): Promise<void> => {
    const refresh = tokenStore.getRefreshToken();
    try {
      if (refresh) {
        await apiClient.post("/api/v1/auth/logout", { refresh_token: refresh }, { auth: false });
      }
    } catch {
      // Log out locally regardless of the network result.
    }
    tokenStore.clear();
    setUser(null);
  };

  const applyUser = (next: UserPublic): void => setUser(next);

  const refreshUser = async (): Promise<void> => {
    const me = await apiClient.get<UserPublic>("/api/v1/users/me");
    setUser(me);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isBootstrapping,
        login,
        loginWithTokenPair,
        register,
        logout,
        applyUser,
        refreshUser,
        bootstrap,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
