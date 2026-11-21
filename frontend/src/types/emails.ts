export type EmailDraftStatus = 'PENDING' | 'APPROVED' | 'SENT' | 'FAILED' | 'REJECTED';

export interface EmailDraftResponse {
  id: string;
  lead_id: string;
  submission_id?: string | null;
  recipient: string;
  subject: string;
  body: string;
  html_body?: string | null;
  preferred_contact: string;
  consent: boolean;
  status: EmailDraftStatus;
  approval_id?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  sent_at?: string | null;
  sent_by?: string | null;
  gmail_message_id?: string | null;
  gmail_thread_id?: string | null;
  error_message?: string | null;
  error_code?: string | null;
  retry_count: number;
  idempotency_key?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailDraftListResponse {
  drafts: EmailDraftResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface EmailSendResponse {
  success: boolean;
  status: 'SENT' | 'FAILED';
  draft_id: string;
  message_id?: string | null;
  thread_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  ambiguous?: boolean;
}
