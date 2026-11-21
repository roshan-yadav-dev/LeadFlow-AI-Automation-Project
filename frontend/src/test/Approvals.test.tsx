import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApprovalsPage } from '../pages/Approvals/ApprovalsPage';
import { approvalsService } from '../services/approvals';

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { username: 'test-admin', role: 'admin' },
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('../services/approvals', () => ({
  approvalsService: {
    listApprovals: vi.fn(),
    getPendingApprovals: vi.fn(),
    recordDecision: vi.fn(),
    expireStale: vi.fn(),
  },
}));

describe('Human Approval Center & Safety Rules', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  it('renders pending approval items with authorization warning and distinct statuses', async () => {
    (approvalsService.getPendingApprovals as any).mockResolvedValue([
      {
        id: 'app-001',
        lead_id: 'lead-123',
        action_type: 'SEND_PROPOSAL_EMAIL',
        requested_by: 'workflow-engine',
        status: 'PENDING',
        execution_status: 'PENDING',
        expires_at: '2026-11-25T15:00:00Z',
        created_at: '2026-11-20T10:00:00Z',
        action_payload: { template: 'enterprise_offer' },
      },
    ]);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ApprovalsPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText('Human-in-the-Loop Approval Center')).toBeInTheDocument();
    expect(screen.getByText(/Safety & Authorization Safeguards/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('SEND_PROPOSAL_EMAIL')).toBeInTheDocument();
      expect(screen.getByText('lead-123')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Authorize/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Reject/i })).toBeInTheDocument();
    });
  });

  it('requires a rejection reason when rejecting an approval', async () => {
    (approvalsService.getPendingApprovals as any).mockResolvedValue([
      {
        id: 'app-002',
        lead_id: 'lead-456',
        action_type: 'ESCALATE_TO_REP',
        requested_by: 'scoring-engine',
        status: 'PENDING',
        execution_status: 'PENDING',
        expires_at: '2026-11-25T15:00:00Z',
        created_at: '2026-11-20T10:00:00Z',
        action_payload: {},
      },
    ]);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ApprovalsPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('lead-456')).toBeInTheDocument();
    });

    // Click reject to open modal
    fireEvent.click(screen.getByRole('button', { name: /Reject/i }));

    // Modal appears requiring reason
    expect(screen.getByText('Reject Action: ESCALATE_TO_REP')).toBeInTheDocument();
    expect(screen.getByText('Rejection Reason (Required) *')).toBeInTheDocument();

    // Type reason
    const input = screen.getByPlaceholderText(/Explain why this action was blocked/i);
    fireEvent.change(input, { target: { value: 'Lead requested no contact' } });

    // Click Block & Reject
    const blockBtn = screen.getByRole('button', { name: /Block & Reject/i });
    expect(blockBtn).toBeInTheDocument();
    fireEvent.click(blockBtn);

    await waitFor(() => {
      expect(approvalsService.recordDecision).toHaveBeenCalledWith('app-002', {
        action: 'REJECT',
        reviewed_by: 'test-admin',
        rejection_reason: 'Lead requested no contact',
      });
    });
  });
});
