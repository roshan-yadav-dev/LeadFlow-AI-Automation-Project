export type ScoreTier = 'HOT' | 'WARM' | 'COLD';

export interface ScoreFactors {
  intent?: string;
  sentiment?: string;
  engagement?: string;
  budget?: string;
  urgency?: string;
  recency?: string;
  complaint_attention_flag?: boolean;
  [key: string]: any;
}

export interface LeadScoreResponse {
  id: string;
  lead_id: string;
  score: number;
  tier: ScoreTier;
  factors: ScoreFactors;
  version: string;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadScoreLeaderboardItem {
  lead_id: string;
  name: string;
  email: string;
  company: string;
  score: number;
  tier: ScoreTier;
  complaint_attention_flag: boolean;
  factors_summary: Record<string, number>;
  calculated_at: string;
}

export interface LeadScoreRecalculateResponse {
  recalculated: number;
  lead_ids: string[];
  results: LeadScoreResponse[];
}
