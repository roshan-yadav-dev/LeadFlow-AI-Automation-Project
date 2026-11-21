import { LeadScoreResponse } from './scoring';
import { FollowUpTaskResponse } from './tasks';
import { ReminderResponse } from './reminders';
import { WorkflowExecutionResponse } from './workflows';
import { ApprovalRequestResponse } from './approvals';
import { GmailIntelligenceDetail } from './gmail';
import { EmailDraftResponse } from './emails';

export interface LeadListItem {
  lead_id: string;
  name: string;
  email: string;
  phone: string;
  company: string;
  service: string;
  requirements: string;
  lead_status: string;
  budget: string;
  consent: boolean | string;
  score: number | null;
  tier: 'HOT' | 'WARM' | 'COLD' | null;
  intent: string | null;
  sentiment: string | null;
  last_interaction: string | null;
  created_at: string | null;
  sheet_row?: number;
}

export interface LeadListResponse {
  leads: LeadListItem[];
  total: number;
  page: number;
  page_size: number;
  crm_synced: boolean;
}

export interface TimelineItem {
  type: 'AUDIT' | 'WORKFLOW_EXECUTION' | 'COMMUNICATION';
  title: string;
  timestamp: string | null;
  details: Record<string, any>;
  actor: string;
}

export interface LeadDetailResponse {
  lead_id: string;
  name: string;
  email: string;
  phone: string;
  company: string;
  service: string;
  requirements: string;
  lead_status: string;
  email_status: 'PENDING' | 'APPROVED' | 'SENT' | 'FAILED' | 'SKIPPED';
  ai_status: 'PENDING' | 'SUCCESS' | 'FAILED';
  budget: string;
  consent: boolean | string;
  created_at: string | null;
  error_message: string;
  score: LeadScoreResponse | null;
  score_history: LeadScoreResponse[];
  tasks: FollowUpTaskResponse[];
  reminders: ReminderResponse[];
  workflow_executions: WorkflowExecutionResponse[];
  approvals: ApprovalRequestResponse[];
  intelligence_records: GmailIntelligenceDetail[];
  email_drafts?: EmailDraftResponse[];
  activity_timeline: TimelineItem[];
}

export interface LeadCreateInput {
  name: string;
  email: string;
  phone?: string | null;
  company?: string | null;
  service: string;
  requirements: string;
  budget?: string | null;
  preferred_contact?: 'email';
  consent: boolean;
}

export interface LeadCreateResponse {
  lead_id: string;
  message: string;
  status: string;
  email: string;
  ai_status: 'SUCCESS' | 'FAILED' | 'PENDING';
  email_status: 'PENDING' | 'SENT' | 'FAILED' | 'SKIPPED';
  email_status_updated: boolean;
  email_error: string | null;
  email_message_id: string | null;
  email_thread_id: string | null;
}
