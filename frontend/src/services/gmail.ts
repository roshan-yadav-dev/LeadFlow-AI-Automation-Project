import api from './api';
import {
  GmailMessageListResponse,
  GmailIntelligenceOverview,
  GmailIntelligenceDetail,
  GmailMatchResponse,
  GmailAnalyzeResponse,
  GmailStatusResponse,
  GmailConnectResponse,
} from '../types/gmail';

export const gmailService = {
  async getStatus(): Promise<GmailStatusResponse> {
    const res = await api.get<GmailStatusResponse>('/gmail/status');
    return res.data;
  },

  async connect(redirectTo?: string): Promise<GmailConnectResponse> {
    const res = await api.post<GmailConnectResponse>('/gmail/connect', null, {
      params: redirectTo ? { redirect_to: redirectTo } : undefined,
    });
    return res.data;
  },

  async syncInbox(): Promise<{ status: string; synchronized: number; error?: string }> {
    const res = await api.post('/gmail/sync');
    return res.data;
  },

  async listMessages(params?: {
    page?: number;
    page_size?: number;
    unread?: boolean;
    sender?: string;
    search?: string;
  }): Promise<GmailMessageListResponse> {
    const res = await api.get<GmailMessageListResponse>('/gmail/messages', { params });
    return res.data;
  },

  async getMessage(messageId: string): Promise<any> {
    const res = await api.get(`/gmail/messages/${messageId}`);
    return res.data;
  },

  async getOverview(): Promise<GmailIntelligenceOverview> {
    const res = await api.get<GmailIntelligenceOverview>('/gmail/intelligence/overview');
    return res.data;
  },

  async matchMessages(): Promise<GmailMatchResponse> {
    const res = await api.post<GmailMatchResponse>('/gmail/intelligence/match');
    return res.data;
  },

  async analyzeMessages(
    batchSize = 20,
    forceReanalysis = false
  ): Promise<GmailAnalyzeResponse> {
    const res = await api.post<GmailAnalyzeResponse>('/gmail/intelligence/analyze', {
      batch_size: batchSize,
      force_reanalysis: forceReanalysis,
    });
    return res.data;
  },

  async getIntelligenceDetail(messageId: string): Promise<GmailIntelligenceDetail> {
    const res = await api.get<GmailIntelligenceDetail>(
      `/gmail/intelligence/messages/${messageId}`
    );
    return res.data;
  },

  async reanalyzeMessage(messageId: string): Promise<GmailAnalyzeResponse> {
    const res = await api.post<GmailAnalyzeResponse>(
      `/gmail/intelligence/messages/${messageId}/reanalyze`
    );
    return res.data;
  },
};
