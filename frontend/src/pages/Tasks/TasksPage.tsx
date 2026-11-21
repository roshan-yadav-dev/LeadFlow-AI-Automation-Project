import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  CheckSquare,
  Plus,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Calendar,
  Phone,
  Mail,
  Users,
  Edit,
} from 'lucide-react';

import { tasksService } from '../../services/tasks';
import {
  FollowUpTaskResponse,
  TaskPriority,
  TaskStatus,
  TaskChannel,
} from '../../types/tasks';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { Modal } from '../../components/common/Modal';
import { Tabs, Tab } from '../../components/common/Tabs';

export const TasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'all';

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [reschedulingTask, setReschedulingTask] = useState<FollowUpTaskResponse | null>(null);
  const [rescheduleDatetime, setRescheduleDatetime] = useState('');

  // Form states for Create Task
  const [newLeadId, setNewLeadId] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newScheduledFor, setNewScheduledFor] = useState('');
  const [newPriority, setNewPriority] = useState<TaskPriority>('MEDIUM');
  const [newChannel, setNewChannel] = useState<TaskChannel>('EMAIL');
  const [newGenReminder, setNewGenReminder] = useState(true);
  const [newReminderMinutes, setNewReminderMinutes] = useState(15);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const {
    data: allTasks,
    isLoading: isLoadingAll,
    error: errorAll,
    refetch: refetchAll,
  } = useQuery({
    queryKey: ['tasks', 'all'],
    queryFn: () => tasksService.listTasks({ page_size: 100 }),
    enabled: activeTab === 'all',
  });

  const {
    data: upcomingTasks,
    isLoading: isLoadingUpcoming,
    error: errorUpcoming,
    refetch: refetchUpcoming,
  } = useQuery({
    queryKey: ['tasks', 'upcoming'],
    queryFn: () => tasksService.getUpcomingTasks(100),
    enabled: activeTab === 'upcoming',
  });

  const {
    data: overdueTasks,
    isLoading: isLoadingOverdue,
    error: errorOverdue,
    refetch: refetchOverdue,
  } = useQuery({
    queryKey: ['tasks', 'overdue'],
    queryFn: () => tasksService.getOverdueTasks(100),
    enabled: activeTab === 'overdue',
  });

  // Mutations
  const createTaskMutation = useMutation({
    mutationFn: () => {
      // Validate ISO date
      if (!newScheduledFor) {
        throw new Error('Scheduled date and time is required');
      }
      const iso = new Date(newScheduledFor).toISOString();
      return tasksService.createTask({
        lead_id: newLeadId.trim(),
        title: newTitle.trim(),
        description: newDescription.trim(),
        scheduled_for: iso,
        timezone: 'Asia/Kolkata',
        priority: newPriority,
        channel: newChannel,
        generate_reminder: newGenReminder,
        reminder_minutes_before: newReminderMinutes,
      });
    },
    onSuccess: () => {
      setIsCreateOpen(false);
      resetCreateForm();
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: any) => {
      setFormError(err.message || 'Failed to create task');
    },
  });

  const completeTaskMutation = useMutation({
    mutationFn: (taskId: string) => tasksService.completeTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const cancelTaskMutation = useMutation({
    mutationFn: (taskId: string) => tasksService.cancelTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const rescheduleTaskMutation = useMutation({
    mutationFn: () => {
      if (!reschedulingTask || !rescheduleDatetime) {
        throw new Error('New scheduled date and time is required');
      }
      const iso = new Date(rescheduleDatetime).toISOString();
      return tasksService.rescheduleTask(reschedulingTask.id, {
        scheduled_for: iso,
        timezone: 'Asia/Kolkata',
      });
    },
    onSuccess: () => {
      setReschedulingTask(null);
      setRescheduleDatetime('');
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: any) => {
      alert(`Reschedule failed: ${err.message}`);
    },
  });

  const resetCreateForm = () => {
    setNewLeadId('');
    setNewTitle('');
    setNewDescription('');
    setNewScheduledFor('');
    setNewPriority('MEDIUM');
    setNewChannel('EMAIL');
    setNewGenReminder(true);
    setNewReminderMinutes(15);
    setFormError(null);
  };

  const handleTabChange = (tabId: string) => {
    searchParams.set('tab', tabId);
    setSearchParams(searchParams);
  };

  const currentTasks =
    activeTab === 'upcoming'
      ? upcomingTasks
      : activeTab === 'overdue'
      ? overdueTasks
      : allTasks;

  const currentLoading =
    activeTab === 'upcoming'
      ? isLoadingUpcoming
      : activeTab === 'overdue'
      ? isLoadingOverdue
      : isLoadingAll;

  const currentError =
    activeTab === 'upcoming'
      ? errorUpcoming
      : activeTab === 'overdue'
      ? errorOverdue
      : errorAll;

  const tabs: Tab[] = [
    { id: 'all', label: 'All Tasks', count: allTasks?.length },
    { id: 'upcoming', label: 'Upcoming Tasks', count: upcomingTasks?.length },
    { id: 'overdue', label: 'Overdue Tasks', count: overdueTasks?.length },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <CheckSquare className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Follow-Up Task Management
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Schedule, reschedule, complete, and track follow-up activities in Asia/Kolkata timezone.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              if (activeTab === 'upcoming') refetchUpcoming();
              else if (activeTab === 'overdue') refetchOverdue();
              else refetchAll();
            }}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            Schedule Follow-Up Task
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={handleTabChange} />

      {/* Task List */}
      {currentLoading ? (
        <TableSkeleton rows={6} columns={6} />
      ) : currentError ? (
        <ErrorBanner message={(currentError as Error).message || 'Failed to load tasks'} />
      ) : !currentTasks || currentTasks.length === 0 ? (
        <EmptyState
          title={
            activeTab === 'overdue'
              ? 'No Overdue Tasks'
              : activeTab === 'upcoming'
              ? 'No Upcoming Tasks'
              : 'No Tasks Scheduled'
          }
          description={
            activeTab === 'overdue'
              ? 'Great job! There are no overdue follow-ups requiring attention.'
              : 'Create a task to stay on top of client communications and follow-ups.'
          }
          action={{
            label: 'Schedule New Task',
            onClick: () => setIsCreateOpen(true),
          }}
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden divide-y divide-slate-100 dark:divide-slate-700">
          {currentTasks.map((task) => (
            <div
              key={task.id}
              className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/60 dark:hover:bg-slate-750/50 transition"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="font-bold text-sm text-slate-900 dark:text-white">
                    {task.title}
                  </span>
                  <StatusBadge status={task.priority} />
                  <StatusBadge status={task.status} />
                  <span className="text-xs text-slate-400 font-mono">
                    Channel: {task.channel}
                  </span>
                </div>

                {task.description && (
                  <p className="text-xs text-slate-600 dark:text-slate-300">
                    {task.description}
                  </p>
                )}

                <div className="flex items-center gap-4 text-xs text-slate-400 pt-1">
                  <span className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                    <Clock className="w-3.5 h-3.5 text-indigo-500" />
                    Scheduled: <DateTimeDisplay isoString={task.scheduled_for} />
                  </span>
                  <span className="font-mono text-slate-500">Lead: {task.lead_id}</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {task.status !== 'COMPLETED' && task.status !== 'CANCELLED' && (
                  <>
                    <button
                      onClick={() => completeTaskMutation.mutate(task.id)}
                      disabled={completeTaskMutation.isPending}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 rounded-lg transition"
                      title="Complete Task"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Complete
                    </button>

                    <button
                      onClick={() => {
                        setReschedulingTask(task);
                        setRescheduleDatetime(
                          task.scheduled_for ? task.scheduled_for.slice(0, 16) : ''
                        );
                      }}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition dark:bg-slate-700 dark:text-slate-200"
                      title="Reschedule Task"
                    >
                      <Calendar className="w-3.5 h-3.5" />
                      Reschedule
                    </button>

                    <button
                      onClick={() => cancelTaskMutation.mutate(task.id)}
                      disabled={cancelTaskMutation.isPending}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                      title="Cancel Task"
                    >
                      <XCircle className="w-4 h-4" />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Task Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          resetCreateForm();
        }}
        title="Schedule Follow-Up Task"
        maxWidth="lg"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createTaskMutation.mutate();
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
              Task Title *
            </label>
            <input
              type="text"
              required
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Call regarding enterprise SLA and pricing"
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Target Date & Time (Asia/Kolkata) *
            </label>
            <input
              type="datetime-local"
              required
              value={newScheduledFor}
              onChange={(e) => setNewScheduledFor(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Submitted as standard ISO-8601 UTC timestamp interpreted in Asia/Kolkata.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Priority
              </label>
              <select
                value={newPriority}
                onChange={(e) => setNewPriority(e.target.value as TaskPriority)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
              >
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="URGENT">URGENT</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Channel
              </label>
              <select
                value={newChannel}
                onChange={(e) => setNewChannel(e.target.value as TaskChannel)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
              >
                <option value="EMAIL">EMAIL</option>
                <option value="CALL">CALL</option>
                <option value="MEETING">MEETING</option>
                <option value="MANUAL">MANUAL</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Description / Notes
            </label>
            <textarea
              rows={2}
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Add key context or points to cover..."
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
            />
          </div>

          <div className="p-3 bg-slate-50 dark:bg-slate-900/40 rounded-lg space-y-2 border border-slate-200 dark:border-slate-700">
            <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={newGenReminder}
                onChange={(e) => setNewGenReminder(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600"
              />
              Auto-generate Linked Reminder
            </label>
            {newGenReminder && (
              <div className="flex items-center gap-2 text-xs text-slate-500 pl-6">
                <span>Remind</span>
                <input
                  type="number"
                  min={0}
                  max={1440}
                  value={newReminderMinutes}
                  onChange={(e) => setNewReminderMinutes(Number(e.target.value))}
                  className="w-16 px-2 py-1 text-xs rounded border border-slate-300 bg-white dark:bg-slate-800"
                />
                <span>minutes before scheduled time</span>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-700">
            <button
              type="button"
              onClick={() => {
                setIsCreateOpen(false);
                resetCreateForm();
              }}
              className="px-4 py-2 text-sm text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createTaskMutation.isPending}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {createTaskMutation.isPending ? 'Scheduling...' : 'Schedule Task'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Reschedule Modal */}
      {reschedulingTask && (
        <Modal
          isOpen={!!reschedulingTask}
          onClose={() => setReschedulingTask(null)}
          title={`Reschedule: ${reschedulingTask.title}`}
          maxWidth="md"
        >
          <div className="space-y-4">
            <p className="text-xs text-slate-500">
              Select a new scheduled date and time for this task (Asia/Kolkata timezone).
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                New Target Date & Time *
              </label>
              <input
                type="datetime-local"
                value={rescheduleDatetime}
                onChange={(e) => setRescheduleDatetime(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setReschedulingTask(null)}
                className="px-4 py-2 text-sm text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={rescheduleTaskMutation.isPending || !rescheduleDatetime}
                onClick={() => rescheduleTaskMutation.mutate()}
                className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {rescheduleTaskMutation.isPending ? 'Rescheduling...' : 'Save Reschedule'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
