export interface AuditLog {
  id: string;
  entity_type: string;
  entity_id: string;
  lead_id: string | null;
  action: string;
  actor: string;
  details: Record<string, any>;
  ip_address: string | null;
  created_at: string;
}
