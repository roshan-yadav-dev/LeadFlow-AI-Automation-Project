import api, { setMemoryCsrfToken } from './api';
import { AuthStatusResponse, LoginResponse } from '../types/auth';

export const authService = {
  async getMe(): Promise<AuthStatusResponse> {
    const res = await api.get<AuthStatusResponse>('/auth/me');
    if (res.data.csrf_token) {
      setMemoryCsrfToken(res.data.csrf_token);
    }
    return res.data;
  },

  async directLogin(): Promise<LoginResponse> {
    try {
      const res = await api.post<LoginResponse>('/auth/direct-login');
      if (res.data.csrf_token) {
        setMemoryCsrfToken(res.data.csrf_token);
      }
      return res.data;
    } catch {
      // Fallback: attempt direct login via /auth/login with configured/default credentials
      return this.login({
        username: (import.meta as any).env?.VITE_DASHBOARD_USERNAME || 'admin',
        password: (import.meta as any).env?.VITE_DASHBOARD_PASSWORD || 'admin123',
      });
    }
  },

  async login(credentials: { username: string; password: string }): Promise<LoginResponse> {
    const res = await api.post<LoginResponse>('/auth/login', credentials);
    if (res.data.csrf_token) {
      setMemoryCsrfToken(res.data.csrf_token);
    }
    return res.data;
  },

  async logout(): Promise<{ status: string }> {
    const res = await api.post<{ status: string }>('/auth/logout');
    setMemoryCsrfToken(null);
    return res.data;
  },
};
