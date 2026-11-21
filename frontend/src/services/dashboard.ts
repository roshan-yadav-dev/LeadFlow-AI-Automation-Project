import api from './api';
import { DashboardOverviewResponse } from '../types/dashboard';

export const dashboardService = {
  async getOverview(): Promise<DashboardOverviewResponse> {
    const res = await api.get<DashboardOverviewResponse>('/dashboard/overview');
    return res.data;
  },
};
