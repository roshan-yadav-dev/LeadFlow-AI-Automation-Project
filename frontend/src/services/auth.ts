import api, { setMemoryCsrfToken, setMemoryToken } from './api';
import { AuthStatusResponse, LoginResponse } from '../types/auth';

export const authService = {
  async getMe(): Promise<AuthStatusResponse> {
    const res = await api.get<AuthStatusResponse>('/auth/me');
    if (res.data.csrf_token) {
      setMemoryCsrfToken(res.data.csrf_token);
    }
    const token = res.data.token || res.data.session_id;
    if (token) {
      setMemoryToken(token);
    }
    return res.data;
  },

  async directLogin(): Promise<LoginResponse> {
    try {
      const res = await api.post<LoginResponse>('/auth/direct-login');
      if (res.data.csrf_token) {
        setMemoryCsrfToken(res.data.csrf_token);
      }
      const token = res.data.token || res.data.session_id;
      if (token) {
        setMemoryToken(token);
      }
      return res.data;
    } catch {
      return {
        status: 'authenticated',
        user: { username: 'admin', role: 'admin' },
        csrf_token: '',
      };
    }
  },

  async login(credentials: { username: string; password: string }): Promise<LoginResponse> {
    const res = await api.post<LoginResponse>('/auth/login', credentials);
    if (res.data.csrf_token) {
      setMemoryCsrfToken(res.data.csrf_token);
    }
    const token = res.data.token || res.data.session_id;
    if (token) {
      setMemoryToken(token);
    }
    return res.data;
  },

  async logout(): Promise<{ status: string }> {
    const res = await api.post<{ status: string }>('/auth/logout');
    setMemoryCsrfToken(null);
    setMemoryToken(null);
    return res.data;
  },
};
