import api from './api';
import {
  ApprovalRequestResponse,
  ApprovalDecisionInput,
  ApprovalExpireResponse,
  ApprovalStatus,
} from '../types/approvals';

export const approvalsService = {
  async listApprovals(params?: {
    status?: ApprovalStatus;
    lead_id?: string;
    page?: number;
    page_size?: number;
  }): Promise<ApprovalRequestResponse[]> {
    const res = await api.get<ApprovalRequestResponse[]>('/automation/approvals', {
      params,
    });
    return res.data;
  },

  async getPendingApprovals(limit = 50, offset = 0): Promise<ApprovalRequestResponse[]> {
    const res = await api.get<ApprovalRequestResponse[]>('/automation/approvals/pending', {
      params: { limit, offset },
    });
    return res.data;
  },

  async getApproval(approvalId: string): Promise<ApprovalRequestResponse> {
    const res = await api.get<ApprovalRequestResponse>(
      `/automation/approvals/${approvalId}`
    );
    return res.data;
  },

  async recordDecision(
    approvalId: string,
    decision: ApprovalDecisionInput
  ): Promise<ApprovalRequestResponse> {
    const res = await api.post<ApprovalRequestResponse>(
      `/automation/approvals/${approvalId}/decision`,
      decision
    );
    return res.data;
  },

  async expireStale(maxAgeHours = 72): Promise<ApprovalExpireResponse> {
    const res = await api.post<ApprovalExpireResponse>(
      '/automation/approvals/expire-stale',
      null,
      { params: { max_age_hours: maxAgeHours } }
    );
    return res.data;
  },
};
