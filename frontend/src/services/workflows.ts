import api from './api';
import {
  WorkflowRuleResponse,
  WorkflowRuleCreateInput,
  WorkflowRuleUpdateInput,
  WorkflowExecutionResponse,
  WorkflowTriggerType,
} from '../types/workflows';

export const workflowsService = {
  async listRules(
    trigger_type?: WorkflowTriggerType,
    is_active?: boolean
  ): Promise<WorkflowRuleResponse[]> {
    const res = await api.get<WorkflowRuleResponse[]>('/automation/rules', {
      params: { trigger_type, is_active },
    });
    return res.data;
  },

  async getRule(ruleId: string): Promise<WorkflowRuleResponse> {
    const res = await api.get<WorkflowRuleResponse>(`/automation/rules/${ruleId}`);
    return res.data;
  },

  async createRule(input: WorkflowRuleCreateInput): Promise<WorkflowRuleResponse> {
    const res = await api.post<WorkflowRuleResponse>('/automation/rules', input);
    return res.data;
  },

  async updateRule(
    ruleId: string,
    input: WorkflowRuleUpdateInput
  ): Promise<WorkflowRuleResponse> {
    const res = await api.patch<WorkflowRuleResponse>(`/automation/rules/${ruleId}`, input);
    return res.data;
  },

  async deleteRule(ruleId: string): Promise<{ deleted: boolean; rule_id: string }> {
    const res = await api.delete<{ deleted: boolean; rule_id: string }>(
      `/automation/rules/${ruleId}`
    );
    return res.data;
  },

  async triggerRule(
    ruleId: string,
    payload: { lead_id: string; context_data?: Record<string, any> }
  ): Promise<WorkflowExecutionResponse> {
    const res = await api.post<WorkflowExecutionResponse>(
      `/automation/rules/${ruleId}/trigger`,
      payload
    );
    return res.data;
  },

  async triggerWorkflowForLead(payload: {
    trigger_type: WorkflowTriggerType;
    lead_id: string;
    context_data?: Record<string, any>;
  }): Promise<WorkflowExecutionResponse[]> {
    const res = await api.post<WorkflowExecutionResponse[]>(
      '/automation/workflows/trigger',
      payload
    );
    return res.data;
  },

  async listExecutions(params?: {
    lead_id?: string;
    rule_id?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<WorkflowExecutionResponse[]> {
    const res = await api.get<WorkflowExecutionResponse[]>('/automation/executions', {
      params,
    });
    return res.data;
  },

  async getExecution(executionId: string): Promise<WorkflowExecutionResponse> {
    const res = await api.get<WorkflowExecutionResponse>(
      `/automation/executions/${executionId}`
    );
    return res.data;
  },
};
