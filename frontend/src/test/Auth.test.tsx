import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../hooks/useAuth';
import { authService } from '../services/auth';

vi.mock('../services/auth', () => ({
  authService: {
    getMe: vi.fn(),
    directLogin: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  },
}));

const TestAuthConsumer: React.FC = () => {
  const { user, isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <div>Loading direct auth...</div>;
  return (
    <div>
      <div data-testid="auth-status">{isAuthenticated ? 'AUTHENTICATED' : 'NOT_AUTHENTICATED'}</div>
      <div data-testid="auth-user">{user?.username}</div>
      <div data-testid="auth-role">{user?.role}</div>
    </div>
  );
};

describe('Direct Authentication & Session Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('automatically performs direct login when unauthenticated', async () => {
    (authService.getMe as any).mockResolvedValue({
      authenticated: false,
      user: null,
      csrf_token: null,
    });
    (authService.directLogin as any).mockResolvedValue({
      status: 'authenticated',
      user: { username: 'admin', role: 'admin' },
      csrf_token: 'test-csrf-123',
    });

    render(
      <AuthProvider>
        <TestAuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('AUTHENTICATED');
      expect(screen.getByTestId('auth-user')).toHaveTextContent('admin');
      expect(screen.getByTestId('auth-role')).toHaveTextContent('admin');
    });

    expect(authService.getMe).toHaveBeenCalledTimes(1);
    expect(authService.directLogin).toHaveBeenCalledTimes(1);
  });

  it('preserves existing session when user is already authenticated', async () => {
    (authService.getMe as any).mockResolvedValue({
      authenticated: true,
      user: { username: 'existing_admin', role: 'admin' },
      csrf_token: 'existing-csrf-token',
    });

    render(
      <AuthProvider>
        <TestAuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('AUTHENTICATED');
      expect(screen.getByTestId('auth-user')).toHaveTextContent('existing_admin');
    });

    expect(authService.getMe).toHaveBeenCalledTimes(1);
    expect(authService.directLogin).not.toHaveBeenCalled();
  });

  it('provides safe fallback operator access if direct login encounters an error', async () => {
    (authService.getMe as any).mockRejectedValue(new Error('Network error'));
    (authService.directLogin as any).mockRejectedValue(new Error('Connection refused'));

    render(
      <AuthProvider>
        <TestAuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('AUTHENTICATED');
      expect(screen.getByTestId('auth-user')).toHaveTextContent('admin');
    });
  });
});
