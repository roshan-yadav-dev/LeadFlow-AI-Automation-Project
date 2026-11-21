import api from './api';
import {
  JobResponse,
  JobStatus,
  AutomationHealthResponse,
  AutomationStatusResponse,
} from '../types/jobs';

export const automationService = {
  async getHealth(): Promise<AutomationHealthResponse> {
    const res = await api.get<AutomationHealthResponse>('/automation/health');
    return res.data;
  },

  async getStatus(): Promise<AutomationStatusResponse> {
    const res = await api.get<AutomationStatusResponse>('/automation/status');
    return res.data;
  },

  async listJobs(params?: {
    status?: JobStatus;
    job_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<JobResponse[]> {
    const res = await api.get<JobResponse[]>('/automation/jobs', { params });
    return res.data;
  },

  async processJobs(batchSize = 10): Promise<Record<string, number>> {
    const res = await api.post<Record<string, number>>('/automation/jobs/process', null, {
      params: { batch_size: batchSize },
    });
    return res.data;
  },
};
