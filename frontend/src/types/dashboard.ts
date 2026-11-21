export interface ChartDataPoint {
  name: string;
  value: number;
  color?: string;
}

export interface DashboardOverviewResponse {
  total_leads: number;
  hot_leads: number;
  warm_leads: number;
  cold_leads: number;
  pending_followups: number;
  overdue_followups: number;
  pending_reminders: number;
  pending_approvals: number;
  active_workflows: number;
  total_executions: number;
  worker_running: boolean;
  temperature_distribution: ChartDataPoint[];
  score_distribution: ChartDataPoint[];
  task_status_distribution: ChartDataPoint[];
  workflow_execution_distribution: ChartDataPoint[];
  lead_creation_trend: Array<{ date: string; count: number }>;
  recent_activity: Array<{
    id: string;
    action: string;
    entity_type: string;
    entity_id: string;
    lead_id: string | null;
    actor: string;
    timestamp: string;
    details: Record<string, any>;
  }>;
  gmail_overview: {
    total_messages: number;
    matched: number;
    unmatched: number;
    analyzed: number;
    pending: number;
  };
}
