export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT';
export type TaskStatus = 'SCHEDULED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
export type TaskChannel = 'EMAIL' | 'CALL' | 'MEETING' | 'MANUAL';

export interface FollowUpTaskResponse {
  id: string;
  lead_id: string;
  title: string;
  description: string;
  scheduled_for: string;
  scheduled_for_local: string;
  timezone: string;
  priority: TaskPriority;
  status: TaskStatus;
  channel: TaskChannel;
  metadata: Record<string, any>;
  idempotency_key: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FollowUpTaskCreateInput {
  lead_id: string;
  title: string;
  description?: string;
  scheduled_for: string;
  timezone?: string;
  priority?: TaskPriority;
  channel?: TaskChannel;
  generate_reminder?: boolean;
  reminder_minutes_before?: number;
  metadata?: Record<string, any>;
  idempotency_key?: string | null;
}

export interface FollowUpTaskUpdateInput {
  status?: TaskStatus;
  description?: string;
  priority?: TaskPriority;
  scheduled_for?: string;
  timezone?: string;
  metadata?: Record<string, any>;
}

export interface FollowUpTaskRescheduleInput {
  scheduled_for: string;
  timezone?: string;
}
