import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Calculator,
  Plus,
  Mail,
  Phone,
  Building,
  CheckCircle,
  Clock,
  Sparkles,
  Calendar,
  AlertTriangle,
  FileText,
  Send,
  Check,
  X,
  AlertCircle,
  ShieldCheck,
} from 'lucide-react';

import { leadsService } from '../../services/leads';
import { scoringService } from '../../services/scoring';
import { tasksService } from '../../services/tasks';
import { emailsService } from '../../services/emails';
import { EmailDraftResponse } from '../../types/emails';
import { ScoreGauge } from '../../components/common/ScoreGauge';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { Tabs, Tab } from '../../components/common/Tabs';
import { CardSkeleton, TableSkeleton } from '../../components/common/LoadingSkeleton';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { EmptyState } from '../../components/common/EmptyState';

export const LeadDetailPage: React.FC = () => {
  const { leadId } = useParams<{ leadId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('overview');

  const {
    data: lead,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['lead', leadId],
    queryFn: () => leadsService.getLead(leadId!),
    enabled: !!leadId,
  });

  const calculateScoreMutation = useMutation({
    mutationFn: () => scoringService.calculateScore(leadId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const completeTaskMutation = useMutation({
    mutationFn: (taskId: string) => tasksService.completeTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const approveDraftMutation = useMutation({
    mutationFn: (draftId: string) => emailsService.approveDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: any) => {
      alert(err.displayMessage || err.message || 'Approval failed');
    },
  });

  const rejectDraftMutation = useMutation({
    mutationFn: ({ draftId, reason }: { draftId: string; reason: string }) =>
      emailsService.rejectDraft(draftId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err: any) => {
      alert(err.displayMessage || err.message || 'Rejection failed');
    },
  });

  const sendDraftMutation = useMutation({
    mutationFn: (draftId: string) => emailsService.sendDraft(draftId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['lead', leadId] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      if (data.success) {
        alert(`Email delivered successfully via Gmail! Message ID: ${data.message_id}`);
      } else {
        alert(`Email dispatch failed: ${data.error_message}`);
      }
    },
    onError: (err: any) => {
      alert(err.displayMessage || err.message || 'Send failed');
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <TableSkeleton rows={5} />
      </div>
    );
  }

  if (error || !lead) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/leads')}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-slate-800"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Leads
        </button>
        <ErrorBanner
          message={error ? (error as Error).message : 'Lead not found'}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  const tabs: Tab[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'communications', label: 'Communications', count: lead.intelligence_records?.length || 0 },
    { id: 'intelligence', label: 'AI Intelligence' },
    { id: 'tasks', label: 'Follow-up Tasks', count: lead.tasks?.length || 0 },
    { id: 'timeline', label: 'Activity Timeline', count: lead.activity_timeline?.length || 0 },
  ];

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/leads')}
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 transition"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                {lead.name || 'Unnamed Lead'}
              </h2>
              <StatusBadge status={lead.lead_status} />
              <StatusBadge status={lead.score?.tier} variant="tier" />
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">ID: {lead.lead_id}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => calculateScoreMutation.mutate()}
            disabled={calculateScoreMutation.isPending}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 transition"
          >
            <Calculator className={`w-3.5 h-3.5 ${calculateScoreMutation.isPending ? 'animate-spin' : ''}`} />
            {calculateScoreMutation.isPending ? 'Calculating...' : 'Recalculate Score'}
          </button>

          <button
            onClick={() => navigate('/tasks')}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Create Task
          </button>
        </div>
      </div>

      {/* Profile Overview Card */}
      <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Lead Score
          </span>
          <div className="mt-2 flex items-baseline gap-3">
            <ScoreGauge score={lead.score?.score} size="lg" />
          </div>
          {lead.score && (
            <p className="text-[11px] text-slate-400 mt-1 font-mono">
              Version: {lead.score.version}
            </p>
          )}
        </div>

        <div>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Contact
          </span>
          <div className="mt-2 space-y-1 text-sm">
            <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
              <Mail className="w-3.5 h-3.5 text-slate-400" />
              <span className="font-mono text-xs">{lead.email || '—'}</span>
            </div>
            {lead.phone && (
              <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <Phone className="w-3.5 h-3.5 text-slate-400" />
                <span>{lead.phone}</span>
              </div>
            )}
          </div>
        </div>

        <div>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Company & Service
          </span>
          <div className="mt-2 space-y-1 text-sm">
            <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
              <Building className="w-3.5 h-3.5 text-slate-400" />
              <span className="font-medium">{lead.company || 'Individual / None'}</span>
            </div>
            <p className="text-xs text-indigo-600 dark:text-indigo-400 font-semibold">
              {lead.service}
            </p>
          </div>
        </div>

        <div>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            CRM & Dispatch Status
          </span>
          <div className="mt-2 space-y-1.5 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-500">Email:</span>
              <StatusBadge status={lead.email_status} size="sm" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-500">AI Status:</span>
              <StatusBadge status={lead.ai_status} size="sm" />
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Inbound Requirements & Inquiry
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-50 dark:bg-slate-900/50 p-4 rounded-lg border border-slate-100 dark:border-slate-800">
              {lead.requirements || 'No specific requirements entered.'}
            </p>

            <div className="grid grid-cols-2 gap-4 pt-2">
              <div>
                <span className="text-xs text-slate-400 font-semibold uppercase">Budget</span>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 mt-1">
                  {lead.budget || 'Not specified'}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-400 font-semibold uppercase">Customer Consent</span>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 mt-1 flex items-center gap-1.5">
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                  Granted
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              AI Scoring Breakdown
            </h3>
            {lead.score ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-xs text-slate-500">Overall Score</span>
                  <ScoreGauge score={lead.score.score} size="md" />
                </div>
                {lead.score.factors && Object.entries(lead.score.factors).map(([factor, val]: [string, any]) => (
                  <div key={factor} className="flex items-center justify-between text-xs py-1">
                    <span className="capitalize text-slate-600 dark:text-slate-400 font-medium">
                      {factor.replace(/_/g, ' ')}
                    </span>
                    <span className="font-semibold text-slate-900 dark:text-slate-100">
                      {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Score Not Calculated"
                description="Click the Recalculate Score button above to generate a deterministic lead score."
              />
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Communications */}
      {activeTab === 'communications' && (
        <div className="space-y-6">
          {/* Outbound AI Email Drafts & Deliveries Section */}
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Send className="w-4 h-4 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                  Outbound AI Email Deliveries & Drafts
                </h3>
              </div>
              <span className="text-xs text-slate-500">
                Form Submission → AI Personalization → Human Signoff → Explicit Gmail Send
              </span>
            </div>

            {lead.email_drafts && lead.email_drafts.length > 0 ? (
              <div className="p-6 space-y-6 divide-y divide-slate-100 dark:divide-slate-700">
                {lead.email_drafts.map((draft: EmailDraftResponse) => (
                  <div key={draft.id} className="pt-6 first:pt-0 space-y-4">
                    {/* Draft Header & Meta */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <StatusBadge status={draft.status} />
                        <span className="font-mono text-xs text-slate-400 font-semibold">
                          ID: {draft.id}
                        </span>
                        <span className="text-xs text-slate-500">
                          To: <strong className="text-slate-800 dark:text-slate-200">{draft.recipient}</strong>
                        </span>
                        {draft.consent ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                            <CheckCircle className="w-3 h-3 text-emerald-600" /> Consent Granted
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded-full">
                            <AlertCircle className="w-3 h-3 text-rose-600" /> Consent Missing
                          </span>
                        )}
                        <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded-full uppercase">
                          Channel: {draft.preferred_contact}
                        </span>
                      </div>
                      <span className="text-xs text-slate-400">
                        Created: <DateTimeDisplay isoString={draft.created_at} />
                      </span>
                    </div>

                    {/* Email Preview Card */}
                    <div className="bg-slate-50 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                      <div className="p-3.5 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/80 space-y-1 text-xs">
                        <div className="flex items-center gap-2 text-slate-500">
                          <span className="w-16 font-semibold uppercase text-[10px]">Subject:</span>
                          <span className="font-bold text-slate-900 dark:text-white text-sm">
                            {draft.subject}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-slate-500">
                          <span className="w-16 font-semibold uppercase text-[10px]">Recipient:</span>
                          <span className="font-mono text-slate-700 dark:text-slate-300">
                            {draft.recipient}
                          </span>
                        </div>
                      </div>
                      <div className="p-4 text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                        {draft.body}
                      </div>
                    </div>

                    {/* Status Banners & Action Controls */}
                    {draft.status === 'PENDING' && (
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/40 rounded-xl text-xs">
                        <div className="flex items-center gap-2 text-amber-900 dark:text-amber-200">
                          <Clock className="w-4 h-4 text-amber-600 flex-shrink-0" />
                          <span>
                            <strong>Pending Human Review:</strong> Review the email draft above before authorizing dispatch.
                          </span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <button
                            onClick={() => approveDraftMutation.mutate(draft.id)}
                            disabled={approveDraftMutation.isPending}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs rounded-lg transition shadow-sm"
                          >
                            <Check className="w-3.5 h-3.5" />
                            {approveDraftMutation.isPending ? 'Authorizing...' : 'Authorize Draft'}
                          </button>
                          <button
                            onClick={() => {
                              const reason = prompt('Please enter rejection reason:');
                              if (reason) {
                                rejectDraftMutation.mutate({ draftId: draft.id, reason });
                              }
                            }}
                            disabled={rejectDraftMutation.isPending}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-semibold text-xs rounded-lg transition"
                          >
                            <X className="w-3.5 h-3.5" />
                            Reject
                          </button>
                        </div>
                      </div>
                    )}

                    {draft.status === 'APPROVED' && (
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-900/50 rounded-xl text-xs">
                        <div className="flex items-center gap-2 text-indigo-900 dark:text-indigo-200">
                          <ShieldCheck className="w-4 h-4 text-indigo-600 flex-shrink-0" />
                          <span>
                            <strong>Authorized by {draft.approved_by || 'Human Operator'}:</strong> Deliberate user action is required to send this email.
                          </span>
                        </div>
                        <button
                          onClick={() => sendDraftMutation.mutate(draft.id)}
                          disabled={sendDraftMutation.isPending}
                          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-lg transition shadow-md shadow-indigo-600/20 flex-shrink-0"
                        >
                          <Send className={`w-3.5 h-3.5 ${sendDraftMutation.isPending ? 'animate-spin' : ''}`} />
                          {sendDraftMutation.isPending ? 'Sending via Gmail...' : 'Send Email via Gmail'}
                        </button>
                      </div>
                    )}

                    {draft.status === 'SENT' && (
                      <div className="p-3.5 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 rounded-xl text-xs space-y-1 text-emerald-900 dark:text-emerald-200">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 font-bold text-emerald-800 dark:text-emerald-300">
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                            Email Successfully Delivered via Gmail API
                          </div>
                          {draft.sent_at && (
                            <span className="text-slate-500">
                              Sent: <DateTimeDisplay isoString={draft.sent_at} />
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-4 text-[11px] font-mono text-emerald-800/80 dark:text-emerald-300/80 pt-0.5">
                          <span>Gmail Message ID: <strong>{draft.gmail_message_id}</strong></span>
                          {draft.gmail_thread_id && (
                            <span>Thread ID: {draft.gmail_thread_id}</span>
                          )}
                          {draft.sent_by && <span>Dispatched by: {draft.sent_by}</span>}
                        </div>
                      </div>
                    )}

                    {draft.status === 'FAILED' && (
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/40 rounded-xl text-xs text-rose-900 dark:text-rose-200">
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2 font-bold text-rose-800 dark:text-rose-300">
                            <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                            Delivery Failed
                          </div>
                          <p className="text-rose-700 dark:text-rose-300/90 pl-6">
                            {draft.error_message || 'An error occurred during Gmail API dispatch.'}
                          </p>
                        </div>
                        <button
                          onClick={() => sendDraftMutation.mutate(draft.id)}
                          disabled={sendDraftMutation.isPending}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs rounded-lg transition shadow-sm flex-shrink-0"
                        >
                          <Send className="w-3.5 h-3.5" />
                          Retry Send
                        </button>
                      </div>
                    )}

                    {draft.status === 'REJECTED' && (
                      <div className="p-3 bg-slate-100 dark:bg-slate-700/50 rounded-lg text-xs text-slate-600 dark:text-slate-300">
                        <span className="font-semibold text-rose-600">Draft Rejected:</span>{' '}
                        {draft.error_message || 'Operator rejected this draft. Sending blocked.'}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center">
                <EmptyState
                  title="No Outbound Email Drafts"
                  description="When a lead is submitted with communication consent, Groq generates a personalized email draft that appears here for human signoff."
                />
              </div>
            )}
          </div>

          {/* Inbound Gmail Intelligence Records Section */}
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 flex justify-between items-center">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                Gmail Inbound & Synchronized Inbox History
              </h3>
            </div>
            {lead.intelligence_records && lead.intelligence_records.length > 0 ? (
              <div className="divide-y divide-slate-100 dark:divide-slate-700">
                {lead.intelligence_records.map((rec) => (
                  <div key={rec.message_id} className="p-4 space-y-2 hover:bg-slate-50/50 transition">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <StatusBadge status={rec.intent_category} />
                        <StatusBadge status={rec.sentiment} />
                        {rec.confidence !== null && (
                          <span className="text-xs text-slate-400">
                            Confidence: {Math.round((rec.confidence || 0) * 100)}%
                          </span>
                        )}
                      </div>
                      <DateTimeDisplay isoString={rec.analyzed_at || rec.created_at} />
                    </div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                      {rec.summary || 'Summary unavailable'}
                    </p>
                    {rec.suggested_next_step && (
                      <p className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">
                        Suggested Action: {rec.suggested_next_step}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8">
                <EmptyState
                  title="No Inbound Messages Synced"
                  description="Synchronize inbox and match messages on the Gmail Intelligence page to associate customer incoming emails."
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: AI Intelligence */}
      {activeTab === 'intelligence' && (
        <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-6">
          <div className="flex items-center gap-2.5">
            <Sparkles className="w-5 h-5 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Deterministic Intelligence & Extraction
            </h3>
          </div>

          {lead.intelligence_records && lead.intelligence_records.length > 0 ? (
            <div className="space-y-6">
              {lead.intelligence_records.map((rec, i) => (
                <div key={i} className="p-5 rounded-xl border border-slate-100 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-900/40 space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-700">
                    <div>
                      <span className="text-xs font-semibold uppercase text-slate-400">Classified Intent</span>
                      <p className="text-base font-bold text-slate-900 dark:text-white mt-0.5">
                        {rec.intent_category || 'OTHER'}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs font-semibold uppercase text-slate-400">Sentiment</span>
                      <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                        {rec.sentiment || 'NEUTRAL'}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs font-semibold uppercase text-slate-400">AI Confidence</span>
                      <p className="text-sm font-semibold text-indigo-600 mt-0.5">
                        {rec.confidence ? `${Math.round(rec.confidence * 100)}%` : '—'}
                      </p>
                    </div>
                  </div>

                  <div>
                    <span className="text-xs font-bold uppercase text-slate-500">Summary</span>
                    <p className="text-sm text-slate-700 dark:text-slate-300 mt-1">{rec.summary}</p>
                  </div>

                  {rec.action_items && rec.action_items.length > 0 && (
                    <div>
                      <span className="text-xs font-bold uppercase text-slate-500">Key Action Items</span>
                      <ul className="list-disc list-inside text-xs text-slate-600 dark:text-slate-300 mt-1 space-y-1">
                        {rec.action_items.map((act, idx) => (
                          <li key={idx}>{act}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No Intelligence Extracted"
              description="No Gmail messages have been analyzed for this lead yet."
            />
          )}
        </div>
      )}

      {/* Tab 4: Follow-up Tasks */}
      {activeTab === 'tasks' && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center bg-slate-50/50">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Associated Follow-Up Tasks
            </h3>
            <button
              onClick={() => navigate('/tasks')}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              + Create New Task
            </button>
          </div>

          {lead.tasks && lead.tasks.length > 0 ? (
            <div className="divide-y divide-slate-100 dark:divide-slate-700">
              {lead.tasks.map((task) => (
                <div key={task.id} className="p-4 flex items-center justify-between hover:bg-slate-50/50 transition">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-900 dark:text-white">
                        {task.title}
                      </span>
                      <StatusBadge status={task.priority} />
                      <StatusBadge status={task.status} />
                    </div>
                    <p className="text-xs text-slate-500 mt-1">{task.description}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" />
                        <DateTimeDisplay isoString={task.scheduled_for} />
                      </span>
                      <span>Channel: {task.channel}</span>
                    </div>
                  </div>

                  {task.status !== 'COMPLETED' && task.status !== 'CANCELLED' && (
                    <button
                      onClick={() => completeTaskMutation.mutate(task.id)}
                      disabled={completeTaskMutation.isPending}
                      className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition"
                    >
                      Mark Complete
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8">
              <EmptyState
                title="No Tasks Scheduled"
                description="There are currently no follow-up tasks associated with this lead."
                action={{
                  label: 'Schedule Follow-Up Task',
                  onClick: () => navigate('/tasks'),
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Tab 5: Activity Timeline */}
      {activeTab === 'timeline' && (
        <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-6">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
            Chronological Audit & Activity Stream
          </h3>

          {lead.activity_timeline && lead.activity_timeline.length > 0 ? (
            <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200 dark:before:bg-slate-700">
              {lead.activity_timeline.map((item, index) => (
                <div key={index} className="relative">
                  <div className="absolute -left-6 top-1 w-2.5 h-2.5 rounded-full bg-indigo-500 ring-4 ring-white dark:ring-slate-800" />
                  <div className="bg-slate-50 dark:bg-slate-900/40 p-4 rounded-xl border border-slate-100 dark:border-slate-800 space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-slate-800 dark:text-slate-200">
                        {item.title}
                      </span>
                      <DateTimeDisplay isoString={item.timestamp} />
                    </div>
                    <p className="text-xs text-slate-400">Actor: {item.actor}</p>
                    {item.details && Object.keys(item.details).length > 0 && (
                      <pre className="text-[11px] bg-white dark:bg-slate-800 p-2 rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 overflow-x-auto mt-2">
                        {JSON.stringify(item.details, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No Activity Events"
              description="No historical timeline records exist for this lead yet."
            />
          )}
        </div>
      )}
    </div>
  );
};
