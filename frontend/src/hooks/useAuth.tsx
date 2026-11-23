import React, { createContext, useContext, useEffect, useState } from 'react';
import { UserProfile } from '../types/auth';
import { authService } from '../services/auth';

interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials?: { username: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>({ username: 'admin', role: 'admin' });
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;

    const initDirectAuth = async () => {
      try {
        const me = await authService.getMe();
        if (me.authenticated && me.user) {
          if (mounted) {
            setUser(me.user);
            setIsAuthenticated(true);
          }
          return;
        }
      } catch {
        // Active session check failed, proceed to direct login
      }

      try {
        const loginRes = await authService.directLogin();
        if (mounted) {
          setUser(loginRes.user);
          setIsAuthenticated(true);
        }
      } catch (err) {
        console.warn('Direct login failed, defaulting user:', err);
        if (mounted) {
          setUser({ username: 'admin', role: 'admin' });
          setIsAuthenticated(true);
        }
      }
    };

    initDirectAuth();

    return () => {
      mounted = false;
    };
  }, []);

  const login = async (credentials?: { username: string; password: string }) => {
    let res;
    if (credentials) {
      res = await authService.login(credentials);
    } else {
      res = await authService.directLogin();
    }
    setUser(res.user);
    setIsAuthenticated(true);
  };

  const logout = async () => {
    try {
      await authService.logout();
    } finally {
      try {
        const res = await authService.directLogin();
        setUser(res.user);
        setIsAuthenticated(true);
      } catch {
        setUser({ username: 'admin', role: 'admin' });
        setIsAuthenticated(true);
      }
    }
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
