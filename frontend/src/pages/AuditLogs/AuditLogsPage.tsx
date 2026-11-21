import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  FileText,
  Search,
  RefreshCw,
  Eye,
  Filter,
  User,
  ShieldAlert,
} from 'lucide-react';

import { auditService } from '../../services/audit';
import { AuditLog } from '../../types/audit';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { Modal } from '../../components/common/Modal';

export const AuditLogsPage: React.FC = () => {
  const [entityType, setEntityType] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [leadIdFilter, setLeadIdFilter] = useState('');
  const [searchEntityId, setSearchEntityId] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const {
    data: logs,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['audit-logs', { entityType, actionFilter, leadIdFilter, page }],
    queryFn: () =>
      auditService.listLogs({
        entity_type: entityType || undefined,
        lead_id: leadIdFilter || undefined,
        page,
        page_size: pageSize,
      }),
  });

  // Client-side search for Entity ID or Action if not matched on server
  const filteredLogs = logs?.filter((log) => {
    if (searchEntityId && !log.entity_id.toLowerCase().includes(searchEntityId.toLowerCase())) {
      return false;
    }
    if (actionFilter && !log.action.toLowerCase().includes(actionFilter.toLowerCase())) {
      return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <FileText className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Immutable Automation Audit Trail
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Historical, read-only event log recording all mutations, scoring evaluations, and approval decisions.
          </p>
        </div>

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 hover:bg-slate-50 transition"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filter Bar */}
      <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {/* Entity Type */}
          <div>
            <select
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 font-semibold"
            >
              <option value="">All Entity Types</option>
              <option value="LEAD_SCORE">LEAD_SCORE</option>
              <option value="FOLLOW_UP_TASK">FOLLOW_UP_TASK</option>
              <option value="REMINDER">REMINDER</option>
              <option value="WORKFLOW_RULE">WORKFLOW_RULE</option>
              <option value="WORKFLOW_EXECUTION">WORKFLOW_EXECUTION</option>
              <option value="APPROVAL_REQUEST">APPROVAL_REQUEST</option>
              <option value="AUTOMATION_JOB">AUTOMATION_JOB</option>
            </select>
          </div>

          {/* Action Filter */}
          <div>
            <input
              type="text"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              placeholder="Filter by action (e.g. CREATED, DECISION)..."
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 font-mono"
            />
          </div>

          {/* Search by Entity ID */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchEntityId}
              onChange={(e) => setSearchEntityId(e.target.value)}
              placeholder="Search Entity ID..."
              className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 font-mono"
            />
          </div>

          {/* Lead ID Filter */}
          <div>
            <input
              type="text"
              value={leadIdFilter}
              onChange={(e) => {
                setLeadIdFilter(e.target.value);
                setPage(1);
              }}
              placeholder="Filter by Lead ID (e.g. LF-101)..."
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 font-mono"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton rows={8} columns={6} />
      ) : error ? (
        <ErrorBanner message={(error as Error).message || 'Failed to load audit logs'} />
      ) : !filteredLogs || filteredLogs.length === 0 ? (
        <EmptyState
          title="No Audit Logs Found"
          description="System events and mutations will be permanently logged here as operations occur."
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3.5">Timestamp</th>
                  <th className="px-4 py-3.5">Entity Type</th>
                  <th className="px-4 py-3.5">Entity ID</th>
                  <th className="px-4 py-3.5">Action</th>
                  <th className="px-4 py-3.5">Actor</th>
                  <th className="px-4 py-3.5">Lead ID</th>
                  <th className="px-4 py-3.5 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700 text-xs">
                {filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    onClick={() => setSelectedLog(log)}
                    className="hover:bg-slate-50/70 transition cursor-pointer"
                  >
                    <td className="px-4 py-3">
                      <DateTimeDisplay isoString={log.created_at} />
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-900 dark:text-white">
                      {log.entity_type}
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                      {log.entity_id}
                    </td>
                    <td className="px-4 py-3 font-bold text-indigo-600 dark:text-indigo-400">
                      {log.action}
                    </td>
                    <td className="px-4 py-3 font-mono">{log.actor}</td>
                    <td className="px-4 py-3 font-mono text-slate-500">
                      {log.lead_id || '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedLog(log);
                        }}
                        className="p-1 rounded-md border border-slate-200 hover:bg-slate-100 text-slate-600 transition"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Audit Detail Modal */}
      {selectedLog && (
        <Modal
          isOpen={!!selectedLog}
          onClose={() => setSelectedLog(null)}
          title={`Audit Record: ${selectedLog.action} (${selectedLog.entity_type})`}
          maxWidth="md"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 dark:bg-slate-900 rounded-lg">
              <div>
                <span className="text-slate-400 uppercase font-semibold">Entity Type</span>
                <p className="font-bold text-slate-900 dark:text-white mt-0.5">{selectedLog.entity_type}</p>
              </div>
              <div>
                <span className="text-slate-400 uppercase font-semibold">Action</span>
                <p className="font-bold text-indigo-600 mt-0.5">{selectedLog.action}</p>
              </div>
              <div>
                <span className="text-slate-400 uppercase font-semibold">Actor</span>
                <p className="font-mono mt-0.5">{selectedLog.actor}</p>
              </div>
              <div>
                <span className="text-slate-400 uppercase font-semibold">IP Address</span>
                <p className="font-mono mt-0.5">{selectedLog.ip_address || 'Internal'}</p>
              </div>
            </div>

            <div>
              <span className="font-bold uppercase text-slate-500">Structured Event Details</span>
              <pre className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto text-[11px] mt-1">
                {JSON.stringify(selectedLog.details, null, 2)}
              </pre>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
