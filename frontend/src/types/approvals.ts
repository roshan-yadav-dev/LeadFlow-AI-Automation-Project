export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED';
export type ApprovalAction = 'APPROVE' | 'REJECT';

export interface ApprovalRequestResponse {
  id: string;
  workflow_execution_id: string | null;
  lead_id: string;
  action_type: string;
  action_payload: Record<string, any>;
  status: ApprovalStatus;
  requested_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  expires_at: string | null;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalDecisionInput {
  action: ApprovalAction;
  reviewed_by: string;
  rejection_reason?: string | null;
}

export interface ApprovalExpireResponse {
  expired_count: number;
  expired_ids: string[];
}
