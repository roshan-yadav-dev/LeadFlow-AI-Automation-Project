import api from './api';
import {
  LeadScoreResponse,
  LeadScoreLeaderboardItem,
  LeadScoreRecalculateResponse,
  ScoreTier,
} from '../types/scoring';

export const scoringService = {
  async getLeaderboard(limit = 50, tier?: ScoreTier): Promise<LeadScoreLeaderboardItem[]> {
    const res = await api.get<LeadScoreLeaderboardItem[]>('/automation/scores/leaderboard', {
      params: { limit, tier },
    });
    return res.data;
  },

  async calculateScore(leadId: string): Promise<LeadScoreResponse> {
    const res = await api.post<LeadScoreResponse>(`/automation/scores/calculate/${leadId}`);
    return res.data;
  },

  async recalculateAllScores(): Promise<LeadScoreRecalculateResponse> {
    const res = await api.post<LeadScoreRecalculateResponse>('/automation/scores/recalculate');
    return res.data;
  },

  async getLatestScore(leadId: string): Promise<LeadScoreResponse> {
    const res = await api.get<LeadScoreResponse>(`/automation/scores/${leadId}`);
    return res.data;
  },

  async getScoreHistory(leadId: string): Promise<LeadScoreResponse[]> {
    const res = await api.get<LeadScoreResponse[]>(`/automation/scores/${leadId}/history`);
    return res.data;
  },
};
