export type JobStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface JobResponse {
  id: string;
  job_type: string;
  payload: Record<string, any>;
  scheduled_at: string;
  status: JobStatus;
  attempts: number;
  max_retries: number;
  locked_until: string | null;
  last_error: string | null;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationHealthResponse {
  status: string;
  database: string;
  worker_running: boolean;
  project: string;
}

export interface AutomationStatusResponse {
  status: string;
  database: string;
  worker_running: boolean;
  default_timezone: string;
  counts: Record<string, number>;
}
