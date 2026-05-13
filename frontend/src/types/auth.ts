export interface AuthUser {
  id: string;
  login_id: string;
  name: string | null;
  email: string | null;
  department?: string | null;
  role: string;
  status: string;
  must_change_password: boolean;
}

export interface LoginResponse {
  status: string;
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
  user: AuthUser;
}

export interface MeResponse {
  status: string;
  user: AuthUser;
}

export interface SignupResponse {
  status: string;
  message: string;
  user: AuthUser;
}
