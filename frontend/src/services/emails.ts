import api from './api';
import {
  EmailDraftResponse,
  EmailDraftListResponse,
  EmailSendResponse,
  EmailDraftStatus,
} from '../types/emails';

export const emailsService = {
  async listDrafts(params?: {
    lead_id?: string;
    status?: EmailDraftStatus;
    page?: number;
    page_size?: number;
  }): Promise<EmailDraftListResponse> {
    const res = await api.get<EmailDraftListResponse>('/automation/emails/drafts', {
      params,
    });
    return res.data;
  },

  async getDraft(draftId: string): Promise<EmailDraftResponse> {
    const res = await api.get<EmailDraftResponse>(
      `/automation/emails/drafts/${draftId}`
    );
    return res.data;
  },

  async approveDraft(
    draftId: string,
    decisionNotes?: string
  ): Promise<EmailDraftResponse> {
    const res = await api.post<EmailDraftResponse>(
      `/automation/emails/drafts/${draftId}/approve`,
      { decision_notes: decisionNotes }
    );
    return res.data;
  },

  async rejectDraft(
    draftId: string,
    rejectionReason: string
  ): Promise<EmailDraftResponse> {
    const res = await api.post<EmailDraftResponse>(
      `/automation/emails/drafts/${draftId}/reject`,
      { rejection_reason: rejectionReason }
    );
    return res.data;
  },

  async sendDraft(draftId: string): Promise<EmailSendResponse> {
    const res = await api.post<EmailSendResponse>(
      `/automation/emails/drafts/${draftId}/send`
    );
    return res.data;
  },

  async sendLeadEmail(leadId: string): Promise<EmailSendResponse> {
    const res = await api.post<EmailSendResponse>(
      `/leads/${leadId}/send-email`
    );
    return res.data;
  },
};
