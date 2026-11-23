export interface UserProfile {
  username: string;
  role: 'admin' | 'operator';
}

export interface AuthStatusResponse {
  status: string;
  authenticated: boolean;
  user: UserProfile | null;
  csrf_token: string | null;
  token?: string | null;
  session_id?: string | null;
}

export interface LoginResponse {
  status: string;
  user: UserProfile;
  csrf_token: string;
  token?: string | null;
  session_id?: string | null;
}
