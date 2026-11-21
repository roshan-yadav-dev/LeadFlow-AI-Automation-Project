export type IntentCategory =
  | 'INTERESTED'
  | 'NOT_INTERESTED'
  | 'FOLLOW_UP'
  | 'MEETING_REQUEST'
  | 'PRICING_INQUIRY'
  | 'INFORMATION_REQUEST'
  | 'NEGOTIATION'
  | 'COMPLAINT'
  | 'OUT_OF_OFFICE'
  | 'OTHER';

export type Sentiment = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | 'MIXED';
export type MatchStatus = 'MATCHED' | 'UNMATCHED' | 'IGNORED' | 'AMBIGUOUS';
export type ClassificationStatus = 'PENDING' | 'ANALYZING' | 'SUCCESS' | 'FAILED' | 'SKIPPED';

export interface GmailMessageListItem {
  message_id: string;
  sender_email: string;
  sender_name: string;
  recipient_email: string;
  subject: string;
  received_timestamp: string;
  snippet: string;
  unread: boolean;
}

export interface GmailMessageListResponse {
  messages: GmailMessageListItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface GmailIntelligenceDetail {
  message_id: string;
  lead_id: string | null;
  match_status: MatchStatus;
  ignore_reason: string | null;
  classification_status: ClassificationStatus;
  intent_category: IntentCategory | null;
  sentiment: Sentiment | null;
  confidence: number | null;
  summary: string | null;
  extracted_information: Record<string, any>;
  action_items: string[];
  suggested_next_step: string | null;
  analysis_error: string | null;
  analyzed_at: string | null;
  created_at: string;
  updated_at: string;
  analysis_history: Array<Record<string, any>>;
}

export interface GmailIntelligenceOverview {
  total_synchronized_messages: number;
  total_eligible_messages: number;
  matched_messages: number;
  unmatched_messages: number;
  ignored_messages: number;
  ambiguous_messages: number;
  analyzed_messages: number;
  pending_analyses: number;
  failed_analyses: number;
  intent_category_counts: Record<string, number>;
  sentiment_counts: Record<string, number>;
}

export interface GmailMatchResponse {
  matched: number;
  unmatched: number;
  ambiguous: number;
  ignored: number;
  processed: number;
}

export interface GmailAnalyzeResponse {
  requested: number;
  succeeded: number;
  failed: number;
  skipped: number;
}
