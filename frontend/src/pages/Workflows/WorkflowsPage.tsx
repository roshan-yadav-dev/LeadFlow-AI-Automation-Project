import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  GitBranch,
  Plus,
  RefreshCw,
  Play,
  Trash2,
  ToggleLeft,
  ToggleRight,
  ShieldAlert,
  Clock,
  Eye,
  CheckCircle,
  XCircle,
  AlertTriangle,
} from 'lucide-react';

import { workflowsService } from '../../services/workflows';
import {
  WorkflowRuleResponse,
  WorkflowExecutionResponse,
  WorkflowTriggerType,
} from '../../types/workflows';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { Modal } from '../../components/common/Modal';
import { ConfirmationModal } from '../../components/common/ConfirmationModal';
import { Tabs, Tab } from '../../components/common/Tabs';

export const WorkflowsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'rules';

  // Rule Editor State
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<WorkflowRuleResponse | null>(null);
  const [ruleName, setRuleName] = useState('');
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>('INTENT_CLASSIFIED');
  const [requiresApproval, setRequiresApproval] = useState(true);
  const [isActive, setIsActive] = useState(true);

  // Conditions
  const [condIntent, setCondIntent] = useState('MEETING_REQUEST');
  const [condTier, setCondTier] = useState('HOT');

  // Action
  const [actionType, setActionType] = useState('CREATE_FOLLOW_UP');
  const [actionTitle, setActionTitle] = useState('Schedule discovery call');
  const [actionDelayHours, setActionDelayHours] = useState(2);
  const [actionPriority, setActionPriority] = useState('HIGH');
  const [editorError, setEditorError] = useState<string | null>(null);

  // Trigger Modal State
  const [triggeringRule, setTriggeringRule] = useState<WorkflowRuleResponse | null>(null);
  const [triggerLeadId, setTriggerLeadId] = useState('');

  // Delete State
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);

  // Selected Execution Inspector
  const [selectedExecution, setSelectedExecution] = useState<WorkflowExecutionResponse | null>(null);

  // Queries
  const {
    data: rules,
    isLoading: isLoadingRules,
    error: errorRules,
    refetch: refetchRules,
  } = useQuery({
    queryKey: ['workflows', 'rules'],
    queryFn: () => workflowsService.listRules(),
    enabled: activeTab === 'rules',
  });

  const {
    data: executions,
    isLoading: isLoadingExecutions,
    error: errorExecutions,
    refetch: refetchExecutions,
  } = useQuery({
    queryKey: ['workflows', 'executions'],
    queryFn: () => workflowsService.listExecutions({ page_size: 100 }),
    enabled: activeTab === 'executions',
  });

  // Mutations
  const saveRuleMutation = useMutation({
    mutationFn: () => {
      const conditions: Record<string, any> = {};
      if (triggerType === 'INTENT_CLASSIFIED') {
        conditions.intent_category = condIntent;
      }
      if (condTier) {
        conditions.tier = [condTier];
      }

      const actions = [
        {
          type: actionType,
          params: {
            title: actionTitle,
            delay_hours: actionDelayHours,
            priority: actionPriority,
            channel: 'EMAIL',
          },
        },
      ];

      if (editingRule) {
        return workflowsService.updateRule(editingRule.id, {
          name: ruleName,
          conditions,
          actions,
          requires_approval: requiresApproval,
          is_active: isActive,
        });
      } else {
        return workflowsService.createRule({
          name: ruleName,
          trigger_type: triggerType,
          conditions,
          actions,
          requires_approval: requiresApproval,
          is_active: isActive,
        });
      }
    },
    onSuccess: () => {
      setIsEditorOpen(false);
      resetEditor();
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
    },
    onError: (err: any) => {
      setEditorError(err.message || 'Failed to save workflow rule');
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ ruleId, nextState }: { ruleId: string; nextState: boolean }) =>
      workflowsService.updateRule(ruleId, { is_active: nextState }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows', 'rules'] });
    },
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => workflowsService.deleteRule(ruleId),
    onSuccess: () => {
      setDeletingRuleId(null);
      queryClient.invalidateQueries({ queryKey: ['workflows', 'rules'] });
    },
  });

  const triggerRuleMutation = useMutation({
    mutationFn: () => {
      if (!triggeringRule || !triggerLeadId) throw new Error('Lead ID is required');
      return workflowsService.triggerRule(triggeringRule.id, {
        lead_id: triggerLeadId.trim(),
        context_data: { source: 'manual_dashboard_trigger' },
      });
    },
    onSuccess: (data) => {
      setTriggeringRule(null);
      setTriggerLeadId('');
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      alert(`Workflow executed! Status: ${data.status} (ID: ${data.id})`);
    },
    onError: (err: any) => {
      alert(`Trigger failed: ${err.message}`);
    },
  });

  const resetEditor = () => {
    setEditingRule(null);
    setRuleName('');
    setTriggerType('INTENT_CLASSIFIED');
    setRequiresApproval(true);
    setIsActive(true);
    setCondIntent('MEETING_REQUEST');
    setCondTier('HOT');
    setActionType('CREATE_FOLLOW_UP');
    setActionTitle('Schedule discovery call');
    setActionDelayHours(2);
    setActionPriority('HIGH');
    setEditorError(null);
  };

  const handleEditClick = (rule: WorkflowRuleResponse) => {
    setEditingRule(rule);
    setRuleName(rule.name);
    setTriggerType(rule.trigger_type);
    setRequiresApproval(rule.requires_approval);
    setIsActive(rule.is_active);
    if (rule.conditions?.intent_category) {
      setCondIntent(rule.conditions.intent_category);
    }
    if (rule.actions && rule.actions.length > 0) {
      setActionType(rule.actions[0].type);
      setActionTitle(rule.actions[0].params?.title || '');
    }
    setIsEditorOpen(true);
  };

  const tabs: Tab[] = [
    { id: 'rules', label: 'Workflow Rules', count: rules?.length },
    { id: 'executions', label: 'Execution History', count: executions?.length },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <GitBranch className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Workflow Automation Engine
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Automate actions with WHEN (trigger), IF (conditions), and THEN (actions) rule logic.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => (activeTab === 'rules' ? refetchRules() : refetchExecutions())}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 hover:bg-slate-50 transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => {
              resetEditor();
              setIsEditorOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            Create Workflow Rule
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={(tabId) => {
          searchParams.set('tab', tabId);
          setSearchParams(searchParams);
        }}
      />

      {/* Tab 1: Rules */}
      {activeTab === 'rules' && (
        <>
          {isLoadingRules ? (
            <TableSkeleton rows={5} columns={5} />
          ) : errorRules ? (
            <ErrorBanner message={(errorRules as Error).message || 'Failed to load rules'} />
          ) : !rules || rules.length === 0 ? (
            <EmptyState
              title="No Workflow Rules Configured"
              description="Define your first automated workflow rule with trigger conditions and actions."
              action={{
                label: 'Create Workflow Rule',
                onClick: () => {
                  resetEditor();
                  setIsEditorOpen(true);
                },
              }}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className={`bg-white dark:bg-slate-800 rounded-xl border p-5 shadow-sm transition-all space-y-4 ${
                    rule.is_active
                      ? 'border-slate-200 dark:border-slate-700'
                      : 'border-slate-200 dark:border-slate-700 opacity-60 bg-slate-50/50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="font-bold text-slate-900 dark:text-white text-base">
                        {rule.name}
                      </h4>
                      <p className="text-xs text-slate-400 font-mono mt-0.5">ID: {rule.id}</p>
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() =>
                          toggleActiveMutation.mutate({
                            ruleId: rule.id,
                            nextState: !rule.is_active,
                          })
                        }
                        className="p-1 text-slate-400 hover:text-indigo-600 transition"
                        title={rule.is_active ? 'Disable rule' : 'Enable rule'}
                      >
                        {rule.is_active ? (
                          <ToggleRight className="w-6 h-6 text-indigo-600" />
                        ) : (
                          <ToggleLeft className="w-6 h-6 text-slate-400" />
                        )}
                      </button>

                      <button
                        onClick={() => handleEditClick(rule)}
                        className="p-1 text-slate-400 hover:text-slate-700 transition"
                        title="Edit rule"
                      >
                        <Eye className="w-4 h-4" />
                      </button>

                      <button
                        onClick={() => setDeletingRuleId(rule.id)}
                        className="p-1 text-slate-400 hover:text-rose-600 transition"
                        title="Delete rule"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Logic Visualizer */}
                  <div className="space-y-2 text-xs bg-slate-50 dark:bg-slate-900/50 p-3 rounded-lg border border-slate-100 dark:border-slate-800">
                    <div className="flex items-center gap-2">
                      <span className="font-bold uppercase text-indigo-600">WHEN:</span>
                      <StatusBadge status={rule.trigger_type} />
                    </div>

                    <div className="flex items-start gap-2">
                      <span className="font-bold uppercase text-amber-600 flex-shrink-0">IF:</span>
                      <pre className="font-mono text-[11px] text-slate-600 dark:text-slate-300">
                        {JSON.stringify(rule.conditions, null, 1)}
                      </pre>
                    </div>

                    <div className="flex items-start gap-2">
                      <span className="font-bold uppercase text-emerald-600 flex-shrink-0">THEN:</span>
                      <div className="space-y-1">
                        {rule.actions?.map((act, i) => (
                          <div key={i} className="font-medium text-slate-700 dark:text-slate-200">
                            &bull; {act.type}: {act.params?.title || JSON.stringify(act.params)}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Safeguards and Manual Trigger */}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-700/60 text-xs">
                    <div className="flex items-center gap-1.5">
                      {rule.requires_approval ? (
                        <span className="inline-flex items-center gap-1 text-amber-600 font-semibold">
                          <ShieldAlert className="w-3.5 h-3.5" />
                          Requires Approval
                        </span>
                      ) : (
                        <span className="text-slate-400">Automatic Execution</span>
                      )}
                    </div>

                    <button
                      onClick={() => setTriggeringRule(rule)}
                      className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-700 font-semibold rounded-lg transition"
                    >
                      <Play className="w-3.5 h-3.5" />
                      Trigger For Lead
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Tab 2: Execution History */}
      {activeTab === 'executions' && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
          {isLoadingExecutions ? (
            <TableSkeleton rows={6} columns={6} />
          ) : errorExecutions ? (
            <ErrorBanner message={(errorExecutions as Error).message || 'Failed to load executions'} />
          ) : !executions || executions.length === 0 ? (
            <EmptyState
              title="No Executions Recorded"
              description="When workflow triggers fire, execution results will appear here."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
                <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 border-b border-slate-200 dark:border-slate-700">
                  <tr>
                    <th className="px-4 py-3.5">Execution ID</th>
                    <th className="px-4 py-3.5">Rule / Event</th>
                    <th className="px-4 py-3.5">Lead ID</th>
                    <th className="px-4 py-3.5">Status</th>
                    <th className="px-4 py-3.5">Triggered At</th>
                    <th className="px-4 py-3.5 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                  {executions.map((exec) => (
                    <tr
                      key={exec.id}
                      onClick={() => setSelectedExecution(exec)}
                      className="hover:bg-slate-50/70 transition cursor-pointer"
                    >
                      <td className="px-4 py-3.5 font-mono text-xs font-bold text-slate-900 dark:text-white">
                        {exec.id}
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex flex-col">
                          <span className="font-semibold text-slate-800 dark:text-slate-200">
                            {exec.trigger_event}
                          </span>
                          <span className="text-[11px] font-mono text-slate-400">
                            Rule: {exec.rule_id}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 font-mono text-xs text-indigo-600 dark:text-indigo-400">
                        {exec.lead_id}
                      </td>
                      <td className="px-4 py-3.5">
                        <StatusBadge status={exec.status} />
                      </td>
                      <td className="px-4 py-3.5">
                        <DateTimeDisplay isoString={exec.created_at} />
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedExecution(exec);
                          }}
                          className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 transition"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Visual Rule Editor Modal */}
      <Modal
        isOpen={isEditorOpen}
        onClose={() => {
          setIsEditorOpen(false);
          resetEditor();
        }}
        title={editingRule ? `Edit Rule: ${editingRule.name}` : 'Create Workflow Automation Rule'}
        maxWidth="xl"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            saveRuleMutation.mutate();
          }}
          className="space-y-4"
        >
          {editorError && (
            <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-lg">
              {editorError}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Rule Name *
            </label>
            <input
              type="text"
              required
              value={ruleName}
              onChange={(e) => setRuleName(e.target.value)}
              placeholder="e.g. Inbound Meeting Request Auto-Responder"
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
          </div>

          {/* Section: WHEN */}
          <div className="p-4 bg-indigo-50/50 dark:bg-indigo-950/20 rounded-xl border border-indigo-100 dark:border-indigo-900/30 space-y-3">
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 flex items-center gap-1.5">
              <span>WHEN</span> Trigger Event Occurs
            </span>
            <select
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value as WorkflowTriggerType)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-slate-800 font-semibold"
            >
              <option value="INTENT_CLASSIFIED">INTENT_CLASSIFIED (Inbound email categorized)</option>
              <option value="SCORE_UPDATED">SCORE_UPDATED (Lead score updated)</option>
              <option value="LEAD_CREATED">LEAD_CREATED (New lead saved)</option>
              <option value="SCHEDULED_TIME">SCHEDULED_TIME (Clock / time elapsed)</option>
              <option value="MANUAL">MANUAL (Operator triggered)</option>
            </select>
          </div>

          {/* Section: IF */}
          <div className="p-4 bg-amber-50/50 dark:bg-amber-950/20 rounded-xl border border-amber-100 dark:border-amber-900/30 space-y-3">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">
              IF Conditions Match
            </span>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                  Intent Category
                </label>
                <select
                  value={condIntent}
                  onChange={(e) => setCondIntent(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-amber-200 bg-white dark:bg-slate-800"
                >
                  <option value="MEETING_REQUEST">MEETING_REQUEST</option>
                  <option value="PRICING_INQUIRY">PRICING_INQUIRY</option>
                  <option value="NEGOTIATION">NEGOTIATION</option>
                  <option value="FOLLOW_UP">FOLLOW_UP</option>
                  <option value="INTERESTED">INTERESTED</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                  Required Temperature Tier
                </label>
                <select
                  value={condTier}
                  onChange={(e) => setCondTier(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-amber-200 bg-white dark:bg-slate-800"
                >
                  <option value="HOT">HOT</option>
                  <option value="WARM">WARM</option>
                  <option value="COLD">COLD</option>
                </select>
              </div>
            </div>
          </div>

          {/* Section: THEN */}
          <div className="p-4 bg-emerald-50/50 dark:bg-emerald-950/20 rounded-xl border border-emerald-100 dark:border-emerald-900/30 space-y-3">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
              THEN Perform Action
            </span>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Action Type</label>
                <select
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-emerald-200 bg-white dark:bg-slate-800"
                >
                  <option value="CREATE_FOLLOW_UP">CREATE_FOLLOW_UP</option>
                  <option value="CREATE_REMINDER">CREATE_REMINDER</option>
                  <option value="UPDATE_LEAD_PRIORITY">UPDATE_LEAD_PRIORITY</option>
                  <option value="REQUEST_HUMAN_APPROVAL">REQUEST_HUMAN_APPROVAL</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Priority</label>
                <select
                  value={actionPriority}
                  onChange={(e) => setActionPriority(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-emerald-200 bg-white dark:bg-slate-800"
                >
                  <option value="URGENT">URGENT</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Action Title / Payload</label>
              <input
                type="text"
                value={actionTitle}
                onChange={(e) => setActionTitle(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-emerald-200 bg-white dark:bg-slate-800"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={requiresApproval}
                onChange={(e) => setRequiresApproval(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600"
              />
              Require Human Approval before dispatching
            </label>

            <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600"
              />
              Rule Active
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-700">
            <button
              type="button"
              onClick={() => {
                setIsEditorOpen(false);
                resetEditor();
              }}
              className="px-4 py-2 text-sm text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saveRuleMutation.isPending}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {saveRuleMutation.isPending ? 'Saving...' : 'Save Workflow Rule'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Manual Trigger Modal */}
      {triggeringRule && (
        <Modal
          isOpen={!!triggeringRule}
          onClose={() => setTriggeringRule(null)}
          title={`Trigger Rule: ${triggeringRule.name}`}
          maxWidth="md"
        >
          <div className="space-y-4">
            <p className="text-xs text-slate-500">
              Manually evaluate and trigger this workflow rule for a specific Lead ID.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Target Lead ID *
              </label>
              <input
                type="text"
                required
                value={triggerLeadId}
                onChange={(e) => setTriggerLeadId(e.target.value)}
                placeholder="e.g. LF-AE9673C5B5C0"
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 font-mono"
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setTriggeringRule(null)}
                className="px-4 py-2 text-sm text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={triggerRuleMutation.isPending || !triggerLeadId}
                onClick={() => triggerRuleMutation.mutate()}
                className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {triggerRuleMutation.isPending ? 'Triggering...' : 'Trigger Execution'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Delete Rule Confirmation Modal */}
      <ConfirmationModal
        isOpen={!!deletingRuleId}
        onClose={() => setDeletingRuleId(null)}
        onConfirm={() => {
          if (deletingRuleId) deleteRuleMutation.mutate(deletingRuleId);
        }}
        title="Delete Workflow Rule?"
        message="This rule will be soft-deleted. Historical executions will be preserved."
        confirmLabel="Delete Rule"
        variant="danger"
        isLoading={deleteRuleMutation.isPending}
      />

      {/* Execution Detail Modal */}
      {selectedExecution && (
        <Modal
          isOpen={!!selectedExecution}
          onClose={() => setSelectedExecution(null)}
          title={`Execution: ${selectedExecution.id}`}
          maxWidth="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-4 p-3 bg-slate-50 dark:bg-slate-900 rounded-lg">
              <div>
                <span className="text-slate-400 font-semibold uppercase">Rule ID</span>
                <p className="font-mono font-bold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedExecution.rule_id}
                </p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Lead ID</span>
                <p className="font-mono font-bold text-indigo-600 mt-0.5">
                  {selectedExecution.lead_id}
                </p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Trigger Event</span>
                <p className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedExecution.trigger_event}
                </p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Status</span>
                <div className="mt-0.5">
                  <StatusBadge status={selectedExecution.status} />
                </div>
              </div>
            </div>

            {selectedExecution.error_message && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg">
                <span className="font-bold">Execution Error:</span> {selectedExecution.error_message}
              </div>
            )}

            <div>
              <span className="font-bold uppercase text-slate-500">Context Data</span>
              <pre className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto text-[11px] mt-1">
                {JSON.stringify(selectedExecution.context_data, null, 2)}
              </pre>
            </div>

            {selectedExecution.result_data && (
              <div>
                <span className="font-bold uppercase text-slate-500">Result Data</span>
                <pre className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto text-[11px] mt-1">
                  {JSON.stringify(selectedExecution.result_data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
};
