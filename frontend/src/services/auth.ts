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
