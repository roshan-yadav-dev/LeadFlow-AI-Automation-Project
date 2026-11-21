import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

// Get CSRF token from cookie if available
function getCsrfTokenFromCookie(): string | null {
  const match = document.cookie.match(new RegExp('(^|;\\s*)leadflow_csrf=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

let memoryCsrfToken: string | null = null;

export function setMemoryCsrfToken(token: string | null) {
  memoryCsrfToken = token;
}

export const api = axios.create({
  baseURL: (import.meta as any).env?.VITE_API_BASE_URL || '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const method = config.method?.toUpperCase();
  if (method && ['POST', 'PATCH', 'DELETE', 'PUT'].includes(method)) {
    const token = memoryCsrfToken || getCsrfTokenFromCookie();
    if (token) {
      config.headers['X-CSRF-Token'] = token;
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string | any }>) => {
    // Standardize error message extraction while preserving the AxiosError object
    const detail = error.response?.data?.detail;
    let message = 'An unexpected error occurred';
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join(', ');
    } else if (error.message) {
      message = error.message;
    }

    (error as any).displayMessage = message;
    return Promise.reject(error);
  }
);

export default api;
