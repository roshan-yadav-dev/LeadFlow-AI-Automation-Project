import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { App } from '../App';
import { authService } from '../services/auth';
import { dashboardService } from '../services/dashboard';

vi.mock('../services/auth', () => ({
  authService: {
    getMe: vi.fn(),
    directLogin: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock('../services/dashboard', () => ({
  dashboardService: {
    getOverview: vi.fn(),
  },
}));

const mockOverviewData = {
  total_leads: 42,
  leads_today: 5,
  hot_leads: 12,
  warm_leads: 18,
  cold_leads: 12,
  pending_followups: 7,
  overdue_followups: 2,
  pending_reminders: 4,
  pending_approvals: 3,
  active_workflows: 5,
  total_executions: 88,
  successful_executions: 80,
  failed_executions: 8,
  worker_running: true,
  temperature_distribution: [
    { name: 'HOT', value: 12, color: '#ef4444' },
    { name: 'WARM', value: 18, color: '#f59e0b' },
    { name: 'COLD', value: 12, color: '#3b82f6' },
  ],
  score_distribution: [
    { name: '0-25', value: 5 },
    { name: '26-50', value: 7 },
    { name: '51-75', value: 18 },
    { name: '76-100', value: 12 },
  ],
  lead_creation_trend: [],
  workflow_execution_distribution: [
    { name: 'SUCCESS', value: 80, color: '#10b981' },
    { name: 'FAILED', value: 8, color: '#ef4444' },
  ],
  task_status_distribution: [
    { name: 'SCHEDULED', value: 7, color: '#3b82f6' },
    { name: 'OVERDUE', value: 2, color: '#ef4444' },
  ],
  recent_activity: [],
  gmail_overview: {
    total_messages: 50,
    matched: 30,
    unmatched: 20,
    analyzed: 25,
    pending: 5,
  },
};

describe('App Root and Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('directly logs in unauthenticated users and renders the dashboard', async () => {
    (authService.getMe as any).mockResolvedValue({
      authenticated: false,
      user: null,
      csrf_token: null,
    });
    (authService.directLogin as any).mockResolvedValue({
      status: 'authenticated',
      user: { username: 'admin', role: 'admin' },
      csrf_token: 'valid-csrf-token',
    });
    (dashboardService.getOverview as any).mockResolvedValue(mockOverviewData);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Total Leads')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
    });

    expect(authService.directLogin).toHaveBeenCalledTimes(1);
  });

  it('loads dashboard directly for already authenticated users', async () => {
    (authService.getMe as any).mockResolvedValue({
      authenticated: true,
      user: { username: 'admin', role: 'admin' },
      csrf_token: 'valid-csrf-token',
    });
    (dashboardService.getOverview as any).mockResolvedValue(mockOverviewData);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Total Leads')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
    });
  });
});
