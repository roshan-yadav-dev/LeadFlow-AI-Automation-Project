import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Cpu,
  RefreshCw,
  Play,
  Activity,
  Database,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
} from 'lucide-react';

import { automationService } from '../../services/automation';
import { JobResponse, JobStatus } from '../../types/jobs';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { ConfirmationModal } from '../../components/common/ConfirmationModal';
import { Modal } from '../../components/common/Modal';

export const JobsPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [isProcessConfirmOpen, setIsProcessConfirmOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<JobResponse | null>(null);

  // Queries
  const { data: health, isLoading: isLoadingHealth } = useQuery({
    queryKey: ['automation', 'health'],
    queryFn: () => automationService.getHealth(),
  });

  const { data: status, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['automation', 'status'],
    queryFn: () => automationService.getStatus(),
  });

  const {
    data: jobs,
    isLoading: isLoadingJobs,
    error: errorJobs,
    refetch: refetchJobs,
    isFetching,
  } = useQuery({
    queryKey: ['automation', 'jobs', statusFilter],
    queryFn: () =>
      automationService.listJobs({
        status: statusFilter ? statusFilter : undefined,
        page_size: 100,
      }),
  });

  // Manual Process Jobs Mutation
  const processJobsMutation = useMutation({
    mutationFn: () => automationService.processJobs(15),
    onSuccess: (data) => {
      setIsProcessConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ['automation'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      alert(`Job batch processed! Result: ${JSON.stringify(data)}`);
    },
    onError: (err: any) => {
      alert(`Process jobs failed: ${err.message}`);
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Cpu className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Automation Queue & Job Worker
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Persistent SQLite queue monitoring, retry mechanics, lease locking, and worker observability.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refetchJobs()}
            disabled={isFetching}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 hover:bg-slate-50 transition"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setIsProcessConfirmOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-black text-white text-sm font-semibold rounded-lg shadow-sm transition"
          >
            <Play className="w-4 h-4" />
            Process Due Jobs Now
          </button>
        </div>
      </div>

      {/* System Health vs Worker Status (Clearly Distinguished) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between">
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase">System API Health</span>
            <div className="mt-1 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-bold text-slate-900 dark:text-white text-sm">
                {health?.status === 'healthy' ? 'HTTP 200 Healthy' : 'Degraded'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">Database: {health?.database || 'connected'}</p>
          </div>
          <Activity className="w-6 h-6 text-emerald-500" />
        </div>

        <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between">
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase">Background Worker</span>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  health?.worker_running ? 'bg-indigo-500' : 'bg-rose-500'
                }`}
              />
              <span className="font-bold text-slate-900 dark:text-white text-sm">
                {health?.worker_running ? 'In-Process Worker Running' : 'Worker Stopped'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">
              Poll interval: 10s &bull; Single-Uvicorn Worker
            </p>
          </div>
          <Cpu className="w-6 h-6 text-indigo-500" />
        </div>

        <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex items-center justify-between">
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase">Queue Counts</span>
            <div className="mt-1 flex items-center gap-3 text-xs font-semibold">
              <span className="text-amber-600">Pending: {status?.counts?.jobs_pending || 0}</span>
              <span className="text-indigo-600">Processing: {status?.counts?.jobs_processing || 0}</span>
              <span className="text-emerald-600">Done: {status?.counts?.jobs_completed || 0}</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">Timezone: {status?.default_timezone || 'Asia/Kolkata'}</p>
          </div>
          <Database className="w-6 h-6 text-slate-400" />
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-500">Filter by Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as JobStatus | '')}
            className="px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 font-semibold"
          >
            <option value="">All Job Statuses</option>
            <option value="PENDING">PENDING</option>
            <option value="PROCESSING">PROCESSING</option>
            <option value="COMPLETED">COMPLETED</option>
            <option value="FAILED">FAILED</option>
            <option value="CANCELLED">CANCELLED</option>
          </select>
        </div>

        <span className="text-xs text-slate-400">
          Showing {jobs?.length || 0} queue jobs
        </span>
      </div>

      {/* Jobs Table */}
      {isLoadingJobs ? (
        <TableSkeleton rows={6} columns={7} />
      ) : errorJobs ? (
        <ErrorBanner message={(errorJobs as Error).message || 'Failed to load jobs'} />
      ) : !jobs || jobs.length === 0 ? (
        <EmptyState
          title="No Queue Jobs Found"
          description="When background jobs (reminders, sync, retries) are enqueued, they appear in this persistent queue."
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3.5">Job ID</th>
                  <th className="px-4 py-3.5">Job Type</th>
                  <th className="px-4 py-3.5">Status</th>
                  <th className="px-4 py-3.5">Attempts</th>
                  <th className="px-4 py-3.5">Scheduled Time</th>
                  <th className="px-4 py-3.5">Last Error</th>
                  <th className="px-4 py-3.5 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => setSelectedJob(job)}
                    className="hover:bg-slate-50/70 transition cursor-pointer"
                  >
                    <td className="px-4 py-3.5 font-mono text-xs font-bold text-slate-900 dark:text-white">
                      {job.id}
                    </td>
                    <td className="px-4 py-3.5 font-semibold text-slate-800 dark:text-slate-200 text-xs">
                      {job.job_type}
                    </td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3.5 text-xs">
                      <span className="font-semibold text-slate-800 dark:text-slate-200">
                        {job.attempts}
                      </span>
                      <span className="text-slate-400"> / {job.max_retries} max</span>
                    </td>
                    <td className="px-4 py-3.5">
                      <DateTimeDisplay isoString={job.scheduled_at} />
                    </td>
                    <td className="px-4 py-3.5 text-xs text-rose-600 max-w-xs truncate">
                      {job.last_error || '—'}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedJob(job);
                        }}
                        className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 transition"
                      >
                        <HelpCircle className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Manual Processing Confirmation Modal */}
      <ConfirmationModal
        isOpen={isProcessConfirmOpen}
        onClose={() => setIsProcessConfirmOpen(false)}
        onConfirm={() => processJobsMutation.mutate()}
        title="Manually Trigger Background Job Batch?"
        message="This will immediately invoke process_due_jobs() for all due jobs in the queue. Note that automated polling is normally handled in the background by the worker."
        confirmLabel="Process Due Jobs"
        variant="primary"
        isLoading={processJobsMutation.isPending}
      />

      {/* Job Details Modal */}
      {selectedJob && (
        <Modal
          isOpen={!!selectedJob}
          onClose={() => setSelectedJob(null)}
          title={`Job Inspector: ${selectedJob.id}`}
          maxWidth="md"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 dark:bg-slate-900 rounded-lg">
              <div>
                <span className="text-slate-400 font-semibold uppercase">Job Type</span>
                <p className="font-bold text-slate-900 dark:text-white mt-0.5">{selectedJob.job_type}</p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Status</span>
                <div className="mt-0.5">
                  <StatusBadge status={selectedJob.status} />
                </div>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Attempts</span>
                <p className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedJob.attempts} of {selectedJob.max_retries}
                </p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Lease / Lock</span>
                <p className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedJob.locked_until ? <DateTimeDisplay isoString={selectedJob.locked_until} /> : 'None'}
                </p>
              </div>
            </div>

            {selectedJob.last_error && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg">
                <span className="font-bold">Last Error:</span> {selectedJob.last_error}
              </div>
            )}

            <div>
              <span className="font-bold uppercase text-slate-500">Job Payload</span>
              <pre className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto text-[11px] mt-1">
                {JSON.stringify(selectedJob.payload, null, 2)}
              </pre>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
