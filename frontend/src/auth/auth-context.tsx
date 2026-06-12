import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

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
  register: (payload: RegisterPayload) => Promise<UserPublic>;
  logout: () => Promise<void>;
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

  // On load, use a persisted refresh token to obtain an access token + user.
  useEffect(() => {
    let active = true;
    void (async () => {
      if (tokenStore.getRefreshToken()) {
        try {
          if (await refreshTokens()) {
            const me = await apiClient.get<UserPublic>("/api/v1/users/me");
            if (active) setUser(me);
          }
        } catch {
          // Ignore: stay unauthenticated.
        }
      }
      if (active) setIsBootstrapping(false);
    })();
    return () => {
      active = false;
    };
  }, []);

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

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: user !== null, isBootstrapping, login, register, logout }}
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
