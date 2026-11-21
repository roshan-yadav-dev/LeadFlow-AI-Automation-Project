export type WorkflowTriggerType =
  | 'LEAD_CREATED'
  | 'INTENT_CLASSIFIED'
  | 'SCORE_UPDATED'
  | 'SCHEDULED_TIME'
  | 'MANUAL';

export type WorkflowExecutionStatus =
  | 'PENDING'
  | 'AWAITING_APPROVAL'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'SKIPPED';

export interface WorkflowRuleResponse {
  id: string;
  name: string;
  trigger_type: WorkflowTriggerType;
  conditions: Record<string, any>;
  actions: Array<Record<string, any>>;
  requires_approval: boolean;
  is_active: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRuleCreateInput {
  name: string;
  trigger_type: WorkflowTriggerType;
  conditions: Record<string, any>;
  actions: Array<Record<string, any>>;
  requires_approval: boolean;
  is_active: boolean;
}

export interface WorkflowRuleUpdateInput {
  name?: string;
  conditions?: Record<string, any>;
  actions?: Array<Record<string, any>>;
  requires_approval?: boolean;
  is_active?: boolean;
}

export interface WorkflowExecutionResponse {
  id: string;
  rule_id: string;
  lead_id: string;
  trigger_event: string;
  status: WorkflowExecutionStatus;
  context_data: Record<string, any>;
  result_data: Record<string, any> | null;
  error_message: string | null;
  idempotency_key: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}
