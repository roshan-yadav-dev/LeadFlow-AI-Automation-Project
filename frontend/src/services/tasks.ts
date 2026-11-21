import api from './api';
import {
  FollowUpTaskResponse,
  FollowUpTaskCreateInput,
  FollowUpTaskUpdateInput,
  FollowUpTaskRescheduleInput,
  TaskPriority,
  TaskStatus,
} from '../types/tasks';

export interface TaskFilterParams {
  lead_id?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  channel?: string;
  upcoming_only?: boolean;
  overdue_only?: boolean;
  page?: number;
  page_size?: number;
}

export const tasksService = {
  async listTasks(params?: TaskFilterParams): Promise<FollowUpTaskResponse[]> {
    const res = await api.get<FollowUpTaskResponse[]>('/automation/tasks', { params });
    return res.data;
  },

  async getUpcomingTasks(limit = 50, offset = 0): Promise<FollowUpTaskResponse[]> {
    const res = await api.get<FollowUpTaskResponse[]>('/automation/tasks/upcoming', {
      params: { limit, offset },
    });
    return res.data;
  },

  async getOverdueTasks(limit = 50, offset = 0): Promise<FollowUpTaskResponse[]> {
    const res = await api.get<FollowUpTaskResponse[]>('/automation/tasks/overdue', {
      params: { limit, offset },
    });
    return res.data;
  },

  async getTask(taskId: string): Promise<FollowUpTaskResponse> {
    const res = await api.get<FollowUpTaskResponse>(`/automation/tasks/${taskId}`);
    return res.data;
  },

  async createTask(input: FollowUpTaskCreateInput): Promise<FollowUpTaskResponse> {
    const res = await api.post<FollowUpTaskResponse>('/automation/tasks', input);
    return res.data;
  },

  async updateTask(taskId: string, input: FollowUpTaskUpdateInput): Promise<FollowUpTaskResponse> {
    const res = await api.patch<FollowUpTaskResponse>(`/automation/tasks/${taskId}`, input);
    return res.data;
  },

  async rescheduleTask(
    taskId: string,
    input: FollowUpTaskRescheduleInput
  ): Promise<FollowUpTaskResponse> {
    const res = await api.post<FollowUpTaskResponse>(
      `/automation/tasks/${taskId}/reschedule`,
      input
    );
    return res.data;
  },

  async completeTask(taskId: string): Promise<FollowUpTaskResponse> {
    const res = await api.post<FollowUpTaskResponse>(`/automation/tasks/${taskId}/complete`);
    return res.data;
  },

  async cancelTask(taskId: string): Promise<FollowUpTaskResponse> {
    const res = await api.post<FollowUpTaskResponse>(`/automation/tasks/${taskId}/cancel`);
    return res.data;
  },
};
