import api from './api';
import { ReminderResponse, ReminderCreateInput, ReminderStatus } from '../types/reminders';

export interface ReminderFilterParams {
  lead_id?: string;
  task_id?: string;
  status?: ReminderStatus;
  page?: number;
  page_size?: number;
}

export const remindersService = {
  async listReminders(params?: ReminderFilterParams): Promise<ReminderResponse[]> {
    const res = await api.get<ReminderResponse[]>('/automation/reminders', { params });
    return res.data;
  },

  async getPendingReminders(limit = 50, offset = 0): Promise<ReminderResponse[]> {
    const res = await api.get<ReminderResponse[]>('/automation/reminders/pending', {
      params: { limit, offset },
    });
    return res.data;
  },

  async createReminder(input: ReminderCreateInput): Promise<ReminderResponse> {
    const res = await api.post<ReminderResponse>('/automation/reminders', input);
    return res.data;
  },

  async dismissReminder(reminderId: string): Promise<ReminderResponse> {
    const res = await api.post<ReminderResponse>(
      `/automation/reminders/${reminderId}/dismiss`
    );
    return res.data;
  },
};
