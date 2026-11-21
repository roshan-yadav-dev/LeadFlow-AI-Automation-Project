import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LeadsPage } from '../pages/Leads/LeadsPage';
import { leadsService } from '../services/leads';

vi.mock('../services/leads', () => ({
  leadsService: {
    listLeads: vi.fn(),
    createLead: vi.fn(),
    getLead: vi.fn(),
  },
}));

vi.mock('../services/scoring', () => ({
  scoringService: {
    calculateScore: vi.fn(),
  },
}));

describe('Leads Management', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  it('renders leads list with columns, metrics, and data', async () => {
    (leadsService.listLeads as any).mockResolvedValue({
      leads: [
        {
          lead_id: 'lead-1',
          name: 'Jane Doe',
          email: 'jane@acme.com',
          phone: '+91 9876543210',
          company: 'Acme Corp',
          service: 'Enterprise AI',
          requirements: 'Needs full automation',
          lead_status: 'NEW',
          budget: '$50k',
          consent: true,
          score: 85,
          tier: 'HOT',
          intent: 'PRICING_INQUIRY',
          sentiment: 'POSITIVE',
          last_interaction: '2026-11-20T12:00:00Z',
          created_at: '2026-11-20T10:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      crm_synced: true,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LeadsPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText('Lead Management')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
      expect(screen.getByText('jane@acme.com')).toBeInTheDocument();
      expect(screen.getByText('Acme Corp')).toBeInTheDocument();
      expect(screen.getByText('HOT')).toBeInTheDocument();
    });
  });

  it('renders empty state when no leads are returned', async () => {
    (leadsService.listLeads as any).mockResolvedValue({
      leads: [],
      total: 0,
      page: 1,
      page_size: 20,
      crm_synced: false,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LeadsPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/No leads found/i)).toBeInTheDocument();
    });
  });
});
