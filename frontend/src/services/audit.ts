import api from './api';
import { AuditLog } from '../types/audit';

export interface AuditLogFilterParams {
  entity_type?: string;
  entity_id?: string;
  lead_id?: string;
  page?: number;
  page_size?: number;
}

export const auditService = {
  async listLogs(params?: AuditLogFilterParams): Promise<AuditLog[]> {
    const res = await api.get<AuditLog[]>('/automation/audit-logs', { params });
    return res.data;
  },
};
