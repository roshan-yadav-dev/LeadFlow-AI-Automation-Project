import { describe, it, expect, vi, beforeEach } from 'vitest';
import { leadsService } from '../services/leads';
import api from '../services/api';

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('LeadsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listLeads calls /leads with parameters and returns response data', async () => {
    const mockData = {
      items: [
        {
          id: 'LF-20261120-001',
          name: 'Jane Doe',
          email: 'jane@example.com',
          status: 'NEW',
          tier: 'HOT',
          lead_score: 85,
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
      total_pages: 1,
    };
    (api.get as any).mockResolvedValue({ data: mockData });

    const params = { status: 'NEW', search: 'Jane' };
    const result = await leadsService.listLeads(params);

    expect(api.get).toHaveBeenCalledWith('/leads', { params });
    expect(result).toEqual(mockData);
  });

  it('getLead calls /leads/:id and returns lead details', async () => {
    const mockLead = {
      lead: {
        id: 'LF-001',
        name: 'John Smith',
        email: 'john@example.com',
      },
    };
    (api.get as any).mockResolvedValue({ data: mockLead });

    const result = await leadsService.getLead('LF-001');

    expect(api.get).toHaveBeenCalledWith('/leads/LF-001');
    expect(result).toEqual(mockLead);
  });

  it('createLead calls POST /leads with payload and returns created lead', async () => {
    const input = {
      name: 'New Lead',
      email: 'new@example.com',
      service: 'Web Development',
      requirements: 'Needs a new modern website',
      consent: true,
    };
    const mockResponse = {
      duplicate: false,
      lead_id: 'LF-NEW-001',
      status: 'NEW',
      message: 'Lead created successfully',
    };
    (api.post as any).mockResolvedValue({ data: mockResponse });

    const result = await leadsService.createLead(input as any);

    expect(api.post).toHaveBeenCalledWith('/leads', input);
    expect(result).toEqual(mockResponse);
  });

  it('getLeadCommunications calls /leads/:id/communications with pagination', async () => {
    const mockComms = { items: [], total: 0 };
    (api.get as any).mockResolvedValue({ data: mockComms });

    const result = await leadsService.getLeadCommunications('LF-001', 2, 10);

    expect(api.get).toHaveBeenCalledWith('/leads/LF-001/communications', {
      params: { page: 2, page_size: 10 },
    });
    expect(result).toEqual(mockComms);
  });
});
