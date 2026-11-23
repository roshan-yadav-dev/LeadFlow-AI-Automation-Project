import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

// Get CSRF token from cookie if available
function getCsrfTokenFromCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^|;\\s*)leadflow_csrf=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

const TOKEN_STORAGE_KEY = 'leadflow_token';

function getStoredToken(): string | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return localStorage.getItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // localStorage might throw in restricted sandbox environments
  }
  return null;
}

function storeToken(token: string | null) {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      if (token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
      } else {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
      }
    }
  } catch {
    // ignore storage errors
  }
}

let memoryToken: string | null = getStoredToken();
let memoryCsrfToken: string | null = null;

export function setMemoryToken(token: string | null) {
  memoryToken = token;
  storeToken(token);
}

export function getMemoryToken(): string | null {
  return memoryToken || getStoredToken();
}

export function setMemoryCsrfToken(token: string | null) {
  memoryCsrfToken = token;
}

export function getApiBaseUrl(): string {
  const envUrl = (import.meta as any).env?.VITE_API_BASE_URL;
  if (!envUrl || typeof envUrl !== 'string') {
    return '/api/v1';
  }
  const clean = envUrl.trim().replace(/\/+$/, '');
  if (!clean.endsWith('/api/v1')) {
    return `${clean}/api/v1`;
  }
  return clean;
}

let activeDirectLoginPromise: Promise<string | null> | null = null;

export async function ensureDirectLoginToken(): Promise<string | null> {
  const current = getMemoryToken();
  if (current) {
    return current;
  }
  if (activeDirectLoginPromise) {
    return activeDirectLoginPromise;
  }
  activeDirectLoginPromise = (async () => {
    try {
      const resp = await axios.post<{
        status: string;
        user: any;
        csrf_token: string;
        token?: string;
        session_id?: string;
      }>(`${getApiBaseUrl()}/auth/direct-login`, {}, { withCredentials: true });

      const tok = resp.data.token || resp.data.session_id || null;
      if (tok) {
        setMemoryToken(tok);
      }
      if (resp.data.csrf_token) {
        setMemoryCsrfToken(resp.data.csrf_token);
      }
      return tok;
    } catch {
      return null;
    } finally {
      activeDirectLoginPromise = null;
    }
  })();
  return activeDirectLoginPromise;
}

export const api = axios.create({
  baseURL: getApiBaseUrl(),
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const url = config.url || '';
  const isAuthEndpoint = url.includes('/auth/direct-login') || url.includes('/auth/login');

  let token = getMemoryToken();
  if (!token && !isAuthEndpoint) {
    try {
      token = await ensureDirectLoginToken();
    } catch {
      // Proceed without token on error
    }
  }

  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
    config.headers['X-Session-ID'] = token;
  }

  const method = config.method?.toUpperCase();
  if (method && ['POST', 'PATCH', 'DELETE', 'PUT'].includes(method)) {
    const csrf = memoryCsrfToken || getCsrfTokenFromCookie();
    if (csrf) {
      config.headers['X-CSRF-Token'] = csrf;
    }
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string | any }>) => {
    if (error.response?.status === 401) {
      setMemoryToken(null);
    }

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
