import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  ShieldAlert,
  Clock,
  CheckCircle,
  XCircle,
  RefreshCw,
  AlertTriangle,
  User,
  Info,
  ExternalLink,
  Send,
} from 'lucide-react';

import { approvalsService } from '../../services/approvals';
import { emailsService } from '../../services/emails';
import { ApprovalRequestResponse, ApprovalStatus } from '../../types/approvals';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { Modal } from '../../components/common/Modal';
import { Tabs, Tab } from '../../components/common/Tabs';
import { useAuth } from '../../hooks/useAuth';

export const ApprovalsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'pending';

  // Decision Modal State
  const [decisionApproval, setDecisionApproval] = useState<ApprovalRequestResponse | null>(null);
  const [decisionAction, setDecisionAction] = useState<'APPROVE' | 'REJECT'>('APPROVE');
  const [rejectionReason, setRejectionReason] = useState('');
  const [decisionError, setDecisionError] = useState<string | null>(null);

  // Inspector
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequestResponse | null>(null);

  // Queries
  const {
    data: pendingApprovals,
    isLoading: isLoadingPending,
    error: errorPending,
    refetch: refetchPending,
  } = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => approvalsService.getPendingApprovals(100),
    enabled: activeTab === 'pending',
  });

  const {
    data: allApprovals,
    isLoading: isLoadingAll,
    error: errorAll,
    refetch: refetchAll,
  } = useQuery({
    queryKey: ['approvals', 'all'],
    queryFn: () => approvalsService.listApprovals({ page_size: 100 }),
    enabled: activeTab === 'all',
  });

  // Mutations
  const recordDecisionMutation = useMutation({
    mutationFn: () => {
      if (!decisionApproval) throw new Error('No approval selected');
      if (decisionAction === 'REJECT' && !rejectionReason.trim()) {
        throw new Error('A reason is strictly required when rejecting an action');
      }
      return approvalsService.recordDecision(decisionApproval.id, {
        action: decisionAction,
        reviewed_by: user?.username || 'operator',
        rejection_reason: decisionAction === 'REJECT' ? rejectionReason.trim() : null,
      });
    },
    onSuccess: () => {
      setDecisionApproval(null);
      setRejectionReason('');
      setDecisionError(null);
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: any) => {
      setDecisionError(err.message || 'Decision failed');
    },
  });

  const expireStaleMutation = useMutation({
    mutationFn: () => approvalsService.expireStale(72),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      alert(`Expired ${data.expired_count} stale approval requests.`);
    },
  });

  const sendApprovedEmailMutation = useMutation({
    mutationFn: (param: { draftId?: string; leadId: string }) => {
      if (param.draftId) {
        return emailsService.sendDraft(param.draftId);
      }
      return emailsService.sendLeadEmail(param.leadId);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['lead'] });
      if (data.success) {
        alert(`Email delivered successfully via Gmail! Message ID: ${data.message_id}`);
      } else {
        alert(`Email send failed: ${data.error_message}`);
      }
    },
    onError: (err: any) => {
      alert(err.displayMessage || err.message || 'Send failed');
    },
  });

  const currentApprovals = activeTab === 'pending' ? pendingApprovals : allApprovals;
  const currentLoading = activeTab === 'pending' ? isLoadingPending : isLoadingAll;
  const currentError = activeTab === 'pending' ? errorPending : errorAll;

  const tabs: Tab[] = [
    { id: 'pending', label: 'Pending Authorizations', count: pendingApprovals?.length },
    { id: 'all', label: 'All Requests History', count: allApprovals?.length },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Human-in-the-Loop Approval Center
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Critical safety guardrail: Authorize or block outbound actions before execution.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => (activeTab === 'pending' ? refetchPending() : refetchAll())}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 hover:bg-slate-50 transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => expireStaleMutation.mutate()}
            disabled={expireStaleMutation.isPending}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition"
            title="Expire requests older than 72 hours"
          >
            <Clock className="w-3.5 h-3.5" />
            Expire Stale Requests
          </button>
        </div>
      </div>

      {/* Safety Notice Banner */}
      <div className="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/40 rounded-xl text-xs space-y-1 text-amber-900 dark:text-amber-200">
        <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-amber-800 dark:text-amber-300">
          <ShieldAlert className="w-4 h-4 text-amber-600" />
          Safety & Authorization Safeguards
        </div>
        <p className="text-amber-800/90 dark:text-amber-300/90 leading-relaxed">
          <strong>PENDING</strong> means no authorization has been granted. <strong>APPROVED</strong> indicates authorization was granted but does not mean execution has completed. <strong>REJECTED</strong> or <strong>EXPIRED</strong> actions remain permanently blocked. Outbound customer communications are never dispatched without explicit verified authorization.
        </p>
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

      {/* Approvals List */}
      {currentLoading ? (
        <TableSkeleton rows={5} columns={6} />
      ) : currentError ? (
        <ErrorBanner message={(currentError as Error).message || 'Failed to load approvals'} />
      ) : !currentApprovals || currentApprovals.length === 0 ? (
        <EmptyState
          title={activeTab === 'pending' ? 'No Pending Approvals' : 'No Approval History'}
          description={
            activeTab === 'pending'
              ? 'All workflow-generated actions are reviewed. No actions are currently blocked.'
              : 'When automated workflows require human signoff, approval requests will appear here.'
          }
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden divide-y divide-slate-100 dark:divide-slate-700">
          {currentApprovals.map((req) => (
            <div
              key={req.id}
              className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50/50 transition"
            >
              <div className="space-y-2 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="font-bold text-sm text-slate-900 dark:text-white">
                    {req.action_type}
                  </span>
                  <StatusBadge status={req.status} />
                  <span className="text-xs text-slate-400 font-mono">
                    ID: {req.id}
                  </span>
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-900/40 rounded-lg text-xs space-y-1 border border-slate-100 dark:border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">
                      Target Lead:
                    </span>
                    <button
                      onClick={() => navigate(`/leads/${req.lead_id}`)}
                      className="text-indigo-600 font-mono font-bold hover:underline flex items-center gap-1"
                    >
                      {req.lead_id} <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>

                  {req.action_payload && (req.action_payload.subject || req.action_payload.title) && (
                    <p className="text-slate-600 dark:text-slate-400">
                      <span className="font-semibold">Subject / Title:</span>{' '}
                      {req.action_payload.subject || req.action_payload.title}
                    </p>
                  )}
                  {req.action_payload && (req.action_payload.recipient || req.action_payload.to_email) && (
                    <p className="text-slate-600 dark:text-slate-400">
                      <span className="font-semibold">Recipient:</span>{' '}
                      {req.action_payload.recipient || req.action_payload.to_email}
                    </p>
                  )}
                  {req.action_payload && req.action_payload.body && (
                    <p className="text-slate-500 text-[11px] italic truncate">
                      <span className="font-semibold">Body Preview:</span>{' '}
                      {String(req.action_payload.body).substring(0, 140)}...
                    </p>
                  )}
                  {req.rejection_reason && (
                    <p className="text-rose-600 font-medium">
                      <span className="font-semibold">Rejection Reason:</span>{' '}
                      {req.rejection_reason}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-4 text-xs text-slate-400 pt-0.5">
                  <span>Requested: <DateTimeDisplay isoString={req.created_at} /></span>
                  {req.expires_at && (
                    <span>Expires: <DateTimeDisplay isoString={req.expires_at} /></span>
                  )}
                  {req.reviewed_by && (
                    <span className="text-slate-600 dark:text-slate-300">
                      Reviewed by: <strong>{req.reviewed_by}</strong> at{' '}
                      <DateTimeDisplay isoString={req.reviewed_at} />
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => setSelectedApproval(req)}
                  className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 text-slate-600 transition"
                  title="Inspect Payload"
                >
                  <Info className="w-4 h-4" />
                </button>

                {req.status === 'APPROVED' && req.action_type === 'SEND_EMAIL' && (
                  <button
                    onClick={() =>
                      sendApprovedEmailMutation.mutate({
                        draftId: req.action_payload?.draft_id,
                        leadId: req.lead_id,
                      })
                    }
                    disabled={sendApprovedEmailMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-lg transition shadow-sm"
                  >
                    <Send className={`w-3.5 h-3.5 ${sendApprovedEmailMutation.isPending ? 'animate-spin' : ''}`} />
                    {sendApprovedEmailMutation.isPending ? 'Sending...' : 'Send Email Now'}
                  </button>
                )}

                {req.status === 'PENDING' && (
                  <>
                    <button
                      onClick={() => {
                        setDecisionApproval(req);
                        setDecisionAction('APPROVE');
                        setRejectionReason('');
                        setDecisionError(null);
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs rounded-lg transition"
                    >
                      <CheckCircle className="w-3.5 h-3.5" />
                      Authorize
                    </button>

                    <button
                      onClick={() => {
                        setDecisionApproval(req);
                        setDecisionAction('REJECT');
                        setRejectionReason('');
                        setDecisionError(null);
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-semibold text-xs rounded-lg transition"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      Reject
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Decision Modal */}
      {decisionApproval && (
        <Modal
          isOpen={!!decisionApproval}
          onClose={() => setDecisionApproval(null)}
          title={
            decisionAction === 'APPROVE'
              ? `Authorize Action: ${decisionApproval.action_type}`
              : `Reject Action: ${decisionApproval.action_type}`
          }
          maxWidth="md"
        >
          <div className="space-y-4">
            {decisionError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-lg">
                {decisionError}
              </div>
            )}

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {decisionAction === 'APPROVE'
                ? 'Granting approval authorizes the automation worker to proceed with executing this action. Ensure all payload parameters are valid.'
                : 'Rejecting this request will permanently block execution. Enter an audit explanation below.'}
            </p>

            <div className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs space-y-1">
              <p><span className="font-semibold">Target Lead:</span> {decisionApproval.lead_id}</p>
              <p><span className="font-semibold">Action:</span> {decisionApproval.action_type}</p>
              <p><span className="font-semibold">Reviewer:</span> {user?.username || 'operator'}</p>
            </div>

            {decisionAction === 'REJECT' && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Rejection Reason (Required) *
                </label>
                <textarea
                  rows={3}
                  required
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder="Explain why this action was blocked (e.g. Lead requested no phone calls, duplicate follow-up)..."
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
                />
              </div>
            )}

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setDecisionApproval(null)}
                className="px-4 py-2 text-sm text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={recordDecisionMutation.isPending}
                onClick={() => recordDecisionMutation.mutate()}
                className={`px-4 py-2 text-sm font-semibold text-white rounded-lg transition ${
                  decisionAction === 'APPROVE'
                    ? 'bg-emerald-600 hover:bg-emerald-700'
                    : 'bg-rose-600 hover:bg-rose-700'
                }`}
              >
                {recordDecisionMutation.isPending
                  ? 'Recording Decision...'
                  : decisionAction === 'APPROVE'
                  ? 'Grant Authorization'
                  : 'Block & Reject'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Inspector Modal */}
      {selectedApproval && (
        <Modal
          isOpen={!!selectedApproval}
          onClose={() => setSelectedApproval(null)}
          title={`Approval Request: ${selectedApproval.id}`}
          maxWidth="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 dark:bg-slate-900 rounded-lg">
              <div>
                <span className="text-slate-400 font-semibold uppercase">Action Type</span>
                <p className="font-bold text-slate-900 dark:text-white mt-0.5">
                  {selectedApproval.action_type}
                </p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Status</span>
                <div className="mt-0.5">
                  <StatusBadge status={selectedApproval.status} />
                </div>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Lead ID</span>
                <p className="font-mono font-bold text-indigo-600 mt-0.5">
                  {selectedApproval.lead_id}
                </p>
              </div>
              <div>
                <span className="text-slate-400 font-semibold uppercase">Requested By</span>
                <p className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedApproval.requested_by}
                </p>
              </div>
            </div>

            <div>
              <span className="font-bold uppercase text-slate-500">Action Payload</span>
              <pre className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto text-[11px] mt-1">
                {JSON.stringify(selectedApproval.action_payload, null, 2)}
              </pre>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
