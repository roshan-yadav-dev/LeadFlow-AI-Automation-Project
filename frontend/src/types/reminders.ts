export type ReminderStatus = 'PENDING' | 'SENT' | 'DISMISSED' | 'FAILED';
export type ReminderChannel = 'INTERNAL_LOG' | 'NOTIFICATION';

export interface ReminderResponse {
  id: string;
  lead_id: string;
  task_id: string | null;
  title: string;
  remind_at: string;
  remind_at_local: string;
  timezone: string;
  status: ReminderStatus;
  recipient: string;
  channel: ReminderChannel;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReminderCreateInput {
  lead_id: string;
  task_id?: string | null;
  title: string;
  remind_at: string;
  timezone?: string;
  recipient?: string;
  channel?: ReminderChannel;
  idempotency_key?: string | null;
}
