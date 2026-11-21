import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  Bell,
  Plus,
  RefreshCw,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Send,
  User,
} from 'lucide-react';

import { remindersService } from '../../services/reminders';
import { ReminderResponse, ReminderStatus } from '../../types/reminders';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { Modal } from '../../components/common/Modal';
import { Tabs, Tab } from '../../components/common/Tabs';

export const RemindersPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'pending';

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newLeadId, setNewLeadId] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newRemindAt, setNewRemindAt] = useState('');
  const [newRecipient, setNewRecipient] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const {
    data: allReminders,
    isLoading: isLoadingAll,
    error: errorAll,
    refetch: refetchAll,
  } = useQuery({
    queryKey: ['reminders', 'all'],
    queryFn: () => remindersService.listReminders({ page_size: 100 }),
    enabled: activeTab === 'all',
  });

  const {
    data: pendingReminders,
    isLoading: isLoadingPending,
    error: errorPending,
    refetch: refetchPending,
  } = useQuery({
    queryKey: ['reminders', 'pending'],
    queryFn: () => remindersService.getPendingReminders(100),
    enabled: activeTab === 'pending',
  });

  // Dismiss Mutation
  const dismissMutation = useMutation({
    mutationFn: (id: string) => remindersService.dismissReminder(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  // Create Mutation
  const createMutation = useMutation({
    mutationFn: () => {
      if (!newRemindAt) throw new Error('Reminder date and time is required');
      const iso = new Date(newRemindAt).toISOString();
      return remindersService.createReminder({
        lead_id: newLeadId.trim(),
        title: newTitle.trim(),
        remind_at: iso,
        timezone: 'Asia/Kolkata',
        recipient: newRecipient.trim(),
      });
    },
    onSuccess: () => {
      setIsCreateOpen(false);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ['reminders'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: any) => {
      setFormError(err.message || 'Failed to create reminder');
    },
  });

  const resetForm = () => {
    setNewLeadId('');
    setNewTitle('');
    setNewRemindAt('');
    setNewRecipient('');
    setFormError(null);
  };

  const handleTabChange = (tabId: string) => {
    searchParams.set('tab', tabId);
    setSearchParams(searchParams);
  };

  const currentReminders = activeTab === 'pending' ? pendingReminders : allReminders;
  const currentLoading = activeTab === 'pending' ? isLoadingPending : isLoadingAll;
  const currentError = activeTab === 'pending' ? errorPending : errorAll;

  const tabs: Tab[] = [
    { id: 'pending', label: 'Pending Reminders', count: pendingReminders?.length },
    { id: 'all', label: 'All Reminders', count: allReminders?.length },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Bell className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Reminder Notifications & Queue
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Automated internal reminders linked to leads and follow-up tasks.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => (activeTab === 'pending' ? refetchPending() : refetchAll())}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            Create Reminder
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={handleTabChange} />

      {/* List */}
      {currentLoading ? (
        <TableSkeleton rows={5} columns={5} />
      ) : currentError ? (
        <ErrorBanner message={(currentError as Error).message || 'Failed to load reminders'} />
      ) : !currentReminders || currentReminders.length === 0 ? (
        <EmptyState
          title={activeTab === 'pending' ? 'No Pending Reminders' : 'No Reminders Created'}
          description={
            activeTab === 'pending'
              ? 'All scheduled reminders have already fired or been dismissed.'
              : 'Create a reminder to get notified before task deadlines.'
          }
          action={{
            label: 'Create New Reminder',
            onClick: () => setIsCreateOpen(true),
          }}
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden divide-y divide-slate-100 dark:divide-slate-700">
          {currentReminders.map((rem) => (
            <div
              key={rem.id}
              className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/50 transition"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="font-bold text-sm text-slate-900 dark:text-white">
                    {rem.title}
                  </span>
                  <StatusBadge status={rem.status} />
                  <span className="text-xs text-slate-400 font-mono">
                    Channel: {rem.channel}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-xs text-slate-400 pt-1">
                  <span className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                    <Clock className="w-3.5 h-3.5 text-indigo-500" />
                    Remind at: <DateTimeDisplay isoString={rem.remind_at} />
                  </span>
                  <span className="font-mono text-slate-500">Lead: {rem.lead_id}</span>
                  {rem.task_id && (
                    <span className="font-mono text-slate-400">Task: {rem.task_id}</span>
                  )}
                  {rem.recipient && <span>Recipient: {rem.recipient}</span>}
                </div>
              </div>

              {/* Actions */}
              {rem.status === 'PENDING' && (
                <button
                  onClick={() => dismissMutation.mutate(rem.id)}
                  disabled={dismissMutation.isPending}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition dark:bg-slate-700 dark:text-slate-200"
                  title="Dismiss Reminder"
                >
                  Dismiss
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create Reminder Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          resetForm();
        }}
        title="Create New Reminder"
        maxWidth="md"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          className="space-y-4"
        >
          {formError && (
            <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-lg">
              {formError}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Lead ID *
            </label>
            <input
              type="text"
              required
              value={newLeadId}
              onChange={(e) => setNewLeadId(e.target.value)}
              placeholder="e.g. LF-AE9673C5B5C0"
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Reminder Title *
            </label>
            <input
              type="text"
              required
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Review pricing proposal before call"
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Remind At (Asia/Kolkata) *
            </label>
            <input
              type="datetime-local"
              required
              value={newRemindAt}
              onChange={(e) => setNewRemindAt(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Recipient Email / Identifier
            </label>
            <input
              type="text"
              value={newRecipient}
              onChange={(e) => setNewRecipient(e.target.value)}
              placeholder="operator@company.com"
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-700">
            <button
              type="button"
              onClick={() => {
                setIsCreateOpen(false);
                resetForm();
              }}
              className="px-4 py-2 text-sm text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Scheduling...' : 'Save Reminder'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
