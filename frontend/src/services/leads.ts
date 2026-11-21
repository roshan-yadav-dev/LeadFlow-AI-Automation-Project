import api from './api';
import {
  LeadListResponse,
  LeadDetailResponse,
  LeadCreateInput,
  LeadCreateResponse,
} from '../types/leads';

export interface LeadFilterParams {
  search?: string;
  status?: string;
  tier?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export const leadsService = {
  async listLeads(params?: LeadFilterParams): Promise<LeadListResponse> {
    const res = await api.get<LeadListResponse>('/leads', { params });
    return res.data;
  },

  async getLead(leadId: string): Promise<LeadDetailResponse> {
    const res = await api.get<LeadDetailResponse>(`/leads/${leadId}`);
    return res.data;
  },

  async createLead(input: LeadCreateInput): Promise<LeadCreateResponse> {
    const res = await api.post<LeadCreateResponse>('/leads', input);
    return res.data;
  },

  async getLeadCommunications(leadId: string, page = 1, pageSize = 25): Promise<any> {
    const res = await api.get(`/leads/${leadId}/communications`, {
      params: { page, page_size: pageSize },
    });
    return res.data;
  },
};
