import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { LoginPage } from '../pages/Login/LoginPage';
import { AuthProvider } from '../hooks/useAuth';
import { authService } from '../services/auth';

vi.mock('../services/auth', () => ({
  authService: {
    getMe: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  },
}));

describe('Auth & Login Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (authService.getMe as any).mockResolvedValue({
      authenticated: false,
      user: null,
      csrf_token: null,
    });
  });

  it('renders login form with username and password fields', async () => {
    render(
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    );

    expect(screen.getByText('LeadFlow AI')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('admin')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('••••••••')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enter Control Dashboard/i })).toBeInTheDocument();
  });

  it('displays error message on invalid credentials (401)', async () => {
    (authService.login as any).mockRejectedValue({
      response: {
        status: 401,
        data: { detail: 'Invalid username or password.' },
      },
    });

    render(
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('admin'), { target: { value: 'wronguser' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'wrongpass' } });
    fireEvent.click(screen.getByRole('button', { name: /Enter Control Dashboard/i }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid username or password/i)).toBeInTheDocument();
    });
  });

  it('displays rate limit error message on 429 response', async () => {
    (authService.login as any).mockRejectedValue({
      response: {
        status: 429,
        data: { detail: 'Too many failed login attempts. Please wait 15 minutes before trying again.' },
      },
    });

    render(
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('admin'), { target: { value: 'testuser' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'testpass' } });
    fireEvent.click(screen.getByRole('button', { name: /Enter Control Dashboard/i }));

    await waitFor(() => {
      expect(screen.getByText(/Too many failed login attempts/i)).toBeInTheDocument();
    });
  });
});
