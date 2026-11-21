import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Mail,
  RefreshCw,
  Sparkles,
  Link as LinkIcon,
  Search,
  ExternalLink,
  Eye,
  CheckCircle,
  AlertCircle,
  Inbox,
  Filter,
} from 'lucide-react';

import { gmailService } from '../../services/gmail';
import {
  GmailMessageListItem,
  GmailIntelligenceDetail,
  GmailIntelligenceOverview,
} from '../../types/gmail';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { StatCard } from '../../components/common/StatCard';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { Modal } from '../../components/common/Modal';

export const GmailPage: React.FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);

  // Queries
  const { data: overview, isLoading: isLoadingOverview } = useQuery({
    queryKey: ['gmail', 'overview'],
    queryFn: () => gmailService.getOverview(),
  });

  const {
    data: messageList,
    isLoading: isLoadingMessages,
    error: errorMessages,
    refetch: refetchMessages,
    isFetching,
  } = useQuery({
    queryKey: ['gmail', 'messages', page, search],
    queryFn: () =>
      gmailService.listMessages({
        page,
        page_size: 25,
        search: search || undefined,
      }),
  });

  const { data: messageDetail, isLoading: isLoadingDetail } = useQuery({
    queryKey: ['gmail', 'detail', selectedMessageId],
    queryFn: () => gmailService.getIntelligenceDetail(selectedMessageId!),
    enabled: !!selectedMessageId,
  });

  // Mutations
  const syncMutation = useMutation({
    mutationFn: () => gmailService.syncInbox(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['gmail'] });
      alert(`Inbox sync completed! ${data.synchronized} messages processed.`);
    },
    onError: (err: any) => {
      alert(`Sync failed: ${err.message}`);
    },
  });

  const matchMutation = useMutation({
    mutationFn: () => gmailService.matchMessages(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['gmail'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      alert(
        `CRM Matching complete! Matched: ${data.matched}, Unmatched: ${data.unmatched}, Ambiguous: ${data.ambiguous}`
      );
    },
    onError: (err: any) => {
      alert(`Matching failed: ${err.message}`);
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: () => gmailService.analyzeMessages(20, false),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['gmail'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['scoring'] });
      alert(
        `Analysis complete! Analyzed: ${data.succeeded}, Skipped: ${data.skipped}, Failed: ${data.failed}`
      );
    },
    onError: (err: any) => {
      alert(`Analysis failed: ${err.message}`);
    },
  });

  const reanalyzeMutation = useMutation({
    mutationFn: (msgId: string) => gmailService.reanalyzeMessage(msgId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gmail'] });
      alert('Message re-analyzed successfully.');
    },
    onError: (err: any) => {
      alert(`Re-analysis failed: ${err.message}`);
    },
  });

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Mail className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Gmail Inbox & Intelligence
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Inbound email ingestion, automated CRM matching, and Groq LLM intent classification.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 transition"
            title="Fetch new messages from Gmail API"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            {syncMutation.isPending ? 'Syncing...' : 'Sync Inbox'}
          </button>

          <button
            onClick={() => matchMutation.mutate()}
            disabled={matchMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 transition"
            title="Associate messages to CRM leads by email"
          >
            <LinkIcon className="w-3.5 h-3.5 text-indigo-500" />
            {matchMutation.isPending ? 'Matching...' : 'Match CRM'}
          </button>

          <button
            onClick={() => analyzeMutation.mutate()}
            disabled={analyzeMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition shadow-sm"
            title="Run Groq LLM intent classification on pending matched messages"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {analyzeMutation.isPending ? 'Analyzing...' : 'Batch Analyze'}
          </button>
        </div>
      </div>

      {/* Intelligence Counters */}
      {overview && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <span className="text-[10px] font-bold text-slate-400 uppercase">Synchronized</span>
            <p className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {overview.total_synchronized_messages}
            </p>
          </div>
          <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <span className="text-[10px] font-bold text-emerald-600 uppercase">Matched Leads</span>
            <p className="text-xl font-bold text-emerald-600 mt-1">{overview.matched_messages}</p>
          </div>
          <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <span className="text-[10px] font-bold text-indigo-600 uppercase">Analyzed</span>
            <p className="text-xl font-bold text-indigo-600 mt-1">{overview.analyzed_messages}</p>
          </div>
          <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <span className="text-[10px] font-bold text-amber-600 uppercase">Pending Analysis</span>
            <p className="text-xl font-bold text-amber-600 mt-1">{overview.pending_analyses}</p>
          </div>
          <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <span className="text-[10px] font-bold text-slate-400 uppercase">Unmatched</span>
            <p className="text-xl font-bold text-slate-700 dark:text-slate-300 mt-1">
              {overview.unmatched_messages}
            </p>
          </div>
          <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <span className="text-[10px] font-bold text-rose-600 uppercase">Failed Analysis</span>
            <p className="text-xl font-bold text-rose-600 mt-1">{overview.failed_analyses}</p>
          </div>
        </div>
      )}

      {/* Messages Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search sender, recipient, subject..."
              className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900"
            />
          </div>
          <span className="text-xs text-slate-400">
            Total Ingested: {messageList?.total || 0}
          </span>
        </div>

        {isLoadingMessages ? (
          <TableSkeleton rows={8} columns={5} />
        ) : errorMessages ? (
          <ErrorBanner
            message={(errorMessages as Error).message || 'Failed to load Gmail messages'}
            onRetry={() => refetchMessages()}
          />
        ) : !messageList || messageList.messages.length === 0 ? (
          <EmptyState
            title="No Messages Found"
            description="Click 'Sync Inbox' to pull recent messages from your configured Gmail account."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3.5">Sender</th>
                  <th className="px-4 py-3.5">Subject</th>
                  <th className="px-4 py-3.5">Snippet Preview</th>
                  <th className="px-4 py-3.5">Received Date</th>
                  <th className="px-4 py-3.5 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {messageList.messages.map((msg) => (
                  <tr
                    key={msg.message_id}
                    onClick={() => setSelectedMessageId(msg.message_id)}
                    className="hover:bg-slate-50/70 transition cursor-pointer"
                  >
                    <td className="px-4 py-3.5">
                      <div className="flex flex-col">
                        <span className="font-semibold text-slate-900 dark:text-white text-xs">
                          {msg.sender_name || msg.sender_email}
                        </span>
                        <span className="text-[11px] text-slate-400 font-mono">
                          {msg.sender_email}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 font-medium text-slate-800 dark:text-slate-200 text-xs">
                      {msg.subject || '(No subject)'}
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-500 max-w-xs truncate">
                      {msg.snippet || '—'}
                    </td>
                    <td className="px-4 py-3.5">
                      <DateTimeDisplay isoString={msg.received_timestamp} />
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedMessageId(msg.message_id);
                        }}
                        className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 transition"
                        title="View Full Intelligence Analysis"
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

        {/* Pagination */}
        {messageList && messageList.total > 25 && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50/50 text-xs text-slate-500">
            <span>Showing Page {page}</span>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page * 25 >= messageList.total}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Intelligence Detail Modal */}
      {selectedMessageId && (
        <Modal
          isOpen={!!selectedMessageId}
          onClose={() => setSelectedMessageId(null)}
          title={`Intelligence Detail: ${selectedMessageId}`}
          maxWidth="2xl"
        >
          {isLoadingDetail ? (
            <TableSkeleton rows={4} columns={2} />
          ) : messageDetail ? (
            <div className="space-y-5 text-xs">
              {/* Header Badges */}
              <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <StatusBadge status={messageDetail.match_status} />
                  <StatusBadge status={messageDetail.classification_status} />
                  <StatusBadge status={messageDetail.intent_category} />
                  <StatusBadge status={messageDetail.sentiment} />
                </div>

                {messageDetail.lead_id && (
                  <button
                    onClick={() => {
                      const id = messageDetail.lead_id;
                      setSelectedMessageId(null);
                      navigate(`/leads/${id}`);
                    }}
                    className="inline-flex items-center gap-1.5 font-bold text-indigo-600 hover:underline"
                  >
                    Matched Lead: {messageDetail.lead_id} <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Summary */}
              {messageDetail.summary && (
                <div>
                  <span className="font-bold uppercase text-slate-500 tracking-wider">
                    LLM Synthesis & Summary
                  </span>
                  <p className="mt-1 text-sm text-slate-700 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-900/40 p-3 rounded-lg border border-slate-100 dark:border-slate-800">
                    {messageDetail.summary}
                  </p>
                </div>
              )}

              {/* Extracted Info */}
              {messageDetail.extracted_information &&
                Object.keys(messageDetail.extracted_information).length > 0 && (
                  <div>
                    <span className="font-bold uppercase text-slate-500 tracking-wider">
                      Extracted Inbound Information
                    </span>
                    <pre className="mt-1 p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto text-[11px]">
                      {JSON.stringify(messageDetail.extracted_information, null, 2)}
                    </pre>
                  </div>
                )}

              {/* Action items */}
              {messageDetail.action_items && messageDetail.action_items.length > 0 && (
                <div>
                  <span className="font-bold uppercase text-slate-500 tracking-wider">
                    Action Items
                  </span>
                  <ul className="mt-1 space-y-1 text-slate-700 dark:text-slate-300 list-disc list-inside">
                    {messageDetail.action_items.map((act, i) => (
                      <li key={i}>{act}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex justify-between items-center pt-3 border-t border-slate-100 dark:border-slate-700">
                <span className="text-slate-400">
                  Analyzed at: <DateTimeDisplay isoString={messageDetail.analyzed_at} />
                </span>

                <button
                  onClick={() => reanalyzeMutation.mutate(messageDetail.message_id)}
                  disabled={reanalyzeMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg transition"
                >
                  <RefreshCw
                    className={`w-3.5 h-3.5 ${reanalyzeMutation.isPending ? 'animate-spin' : ''}`}
                  />
                  Force Re-Analyze
                </button>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No Intelligence Found"
              description="This message has not been analyzed or matched to a lead yet."
            />
          )}
        </Modal>
      )}
    </div>
  );
};
