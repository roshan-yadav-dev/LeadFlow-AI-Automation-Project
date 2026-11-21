import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Award,
  RefreshCw,
  Calculator,
  Flame,
  Sun,
  Snowflake,
  AlertTriangle,
  History,
  Info,
  CheckCircle,
} from 'lucide-react';

import { scoringService } from '../../services/scoring';
import { ScoreTier, LeadScoreResponse } from '../../types/scoring';
import { ScoreGauge } from '../../components/common/ScoreGauge';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { ConfirmationModal } from '../../components/common/ConfirmationModal';
import { Modal } from '../../components/common/Modal';

export const LeadScoringPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [tierFilter, setTierFilter] = useState<ScoreTier | ''>('');
  const [isRecalculateConfirmOpen, setIsRecalculateConfirmOpen] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [singleLeadIdInput, setSingleLeadIdInput] = useState('');

  // Fetch Leaderboard
  const {
    data: leaderboard,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['scoring', 'leaderboard', tierFilter],
    queryFn: () =>
      scoringService.getLeaderboard(100, tierFilter ? tierFilter : undefined),
  });

  // Fetch Score History for selected lead
  const { data: scoreHistory, isLoading: isLoadingHistory } = useQuery({
    queryKey: ['scoring', 'history', selectedLeadId],
    queryFn: () => scoringService.getScoreHistory(selectedLeadId!),
    enabled: !!selectedLeadId,
  });

  // Recalculate All Mutation
  const recalculateAllMutation = useMutation({
    mutationFn: () => scoringService.recalculateAllScores(),
    onSuccess: (data) => {
      setIsRecalculateConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ['scoring'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      alert(`Successfully recalculated scores for ${data.recalculated} leads.`);
    },
  });

  // Calculate Single Lead Mutation
  const calculateSingleMutation = useMutation({
    mutationFn: (leadId: string) => scoringService.calculateScore(leadId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['scoring'] });
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setSelectedLeadId(data.lead_id);
      setSingleLeadIdInput('');
    },
    onError: (err: Error) => {
      alert(`Calculation failed: ${err.message}`);
    },
  });

  const handleSingleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!singleLeadIdInput.trim()) return;
    calculateSingleMutation.mutate(singleLeadIdInput.trim());
  };

  return (
    <div className="space-y-6">
      {/* Header & Main Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Award className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              AI Lead Scoring Engine
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic, 100-point multi-factor scoring based on intent, sentiment, engagement, budget, urgency, and recency.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
            title="Refresh Leaderboard"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => setIsRecalculateConfirmOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
          >
            <RefreshCw className="w-4 h-4" />
            Recalculate All Scores
          </button>
        </div>
      </div>

      {/* Calculate Single Lead Form & Filter Bar */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* On-demand calculation box */}
        <div className="md:col-span-2 bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <form onSubmit={handleSingleSubmit} className="flex gap-3">
            <div className="relative flex-1">
              <Calculator className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={singleLeadIdInput}
                onChange={(e) => setSingleLeadIdInput(e.target.value)}
                placeholder="Enter Lead ID to calculate score (e.g. LF-AE9673C5B5C0)..."
                className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={calculateSingleMutation.isPending || !singleLeadIdInput.trim()}
              className="px-4 py-2 text-sm font-semibold text-white bg-slate-900 hover:bg-black rounded-lg transition disabled:opacity-40"
            >
              {calculateSingleMutation.isPending ? 'Calculating...' : 'Calculate'}
            </button>
          </form>
        </div>

        {/* Temperature filter selector */}
        <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value as ScoreTier | '')}
            className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 font-semibold"
          >
            <option value="">All Tiers (HOT, WARM, COLD)</option>
            <option value="HOT">HOT Leads Only (&ge; 70)</option>
            <option value="WARM">WARM Leads Only (40-69)</option>
            <option value="COLD">COLD Leads Only (&lt; 40)</option>
          </select>
        </div>
      </div>

      {/* Leaderboard Table */}
      {isLoading ? (
        <TableSkeleton rows={8} columns={6} />
      ) : error ? (
        <ErrorBanner
          message={(error as Error).message || 'Failed to load leaderboard'}
          onRetry={() => refetch()}
        />
      ) : !leaderboard || leaderboard.length === 0 ? (
        <EmptyState
          title="No Scored Leads"
          description="Click 'Recalculate All Scores' to run the deterministic scoring algorithm across your CRM leads."
          action={{
            label: 'Recalculate All Scores',
            onClick: () => setIsRecalculateConfirmOpen(true),
          }}
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 flex justify-between items-center">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Scored Leads Leaderboard ({leaderboard.length})
            </h3>
            <span className="text-xs text-slate-400">Ranked by score DESC</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3.5">Rank</th>
                  <th className="px-4 py-3.5">Lead / Company</th>
                  <th className="px-4 py-3.5">Email</th>
                  <th className="px-4 py-3.5">Score</th>
                  <th className="px-4 py-3.5">Temperature</th>
                  <th className="px-4 py-3.5">Flags</th>
                  <th className="px-4 py-3.5">Calculated At</th>
                  <th className="px-4 py-3.5 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {leaderboard.map((item, index) => (
                  <tr
                    key={item.lead_id}
                    onClick={() => setSelectedLeadId(item.lead_id)}
                    className="hover:bg-slate-50/80 dark:hover:bg-slate-750/50 transition cursor-pointer"
                  >
                    <td className="px-4 py-3.5 font-bold text-slate-400 text-xs">
                      #{index + 1}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-col">
                        <span className="font-semibold text-slate-900 dark:text-white">
                          {item.name || 'Unnamed Lead'}
                        </span>
                        <span className="text-xs text-slate-400">
                          {item.company || item.lead_id}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs">{item.email || '—'}</td>
                    <td className="px-4 py-3.5">
                      <ScoreGauge score={item.score} size="md" />
                    </td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={item.tier} variant="tier" />
                    </td>
                    <td className="px-4 py-3.5">
                      {item.complaint_attention_flag && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-700">
                          <AlertTriangle className="w-3 h-3" />
                          Complaint Flag
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <DateTimeDisplay isoString={item.calculated_at} />
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedLeadId(item.lead_id);
                        }}
                        className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 transition"
                        title="Inspect Score Breakdown & History"
                      >
                        <Info className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recalculate All Confirmation Modal */}
      <ConfirmationModal
        isOpen={isRecalculateConfirmOpen}
        onClose={() => setIsRecalculateConfirmOpen(false)}
        onConfirm={() => recalculateAllMutation.mutate()}
        title="Recalculate All Lead Scores?"
        message="This will execute the deterministic Python scoring algorithm across all leads currently stored in Google Sheets and local intelligence databases. Are you sure you want to proceed?"
        confirmLabel="Recalculate All"
        variant="primary"
        isLoading={recalculateAllMutation.isPending}
      />

      {/* Score Details & History Modal */}
      {selectedLeadId && (
        <Modal
          isOpen={!!selectedLeadId}
          onClose={() => setSelectedLeadId(null)}
          title={`Score Audit & History: ${selectedLeadId}`}
          maxWidth="2xl"
        >
          <div className="space-y-6">
            <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-800">
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase">Selected Lead</p>
                <p className="text-base font-bold text-slate-900 dark:text-white font-mono">
                  {selectedLeadId}
                </p>
              </div>
              <button
                onClick={() => {
                  const id = selectedLeadId;
                  setSelectedLeadId(null);
                  navigate(`/leads/${id}`);
                }}
                className="px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 bg-indigo-50 rounded-lg transition"
              >
                View Full Lead Profile &rarr;
              </button>
            </div>

            {/* Score History List */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
                <History className="w-4 h-4 text-indigo-500" />
                Score Revision History
              </h4>

              {isLoadingHistory ? (
                <TableSkeleton rows={3} columns={4} />
              ) : scoreHistory && scoreHistory.length > 0 ? (
                <div className="divide-y divide-slate-100 dark:divide-slate-700/60 border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                  {scoreHistory.map((s, idx) => (
                    <div key={s.id || idx} className="p-4 space-y-3 bg-white dark:bg-slate-800">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <ScoreGauge score={s.score} size="md" />
                          <StatusBadge status={s.tier} variant="tier" />
                          <span className="text-xs text-slate-400 font-mono">
                            Ver: {s.version}
                          </span>
                        </div>
                        <DateTimeDisplay isoString={s.created_at} />
                      </div>

                      {s.factors && (
                        <div className="p-3 bg-slate-50 dark:bg-slate-900/50 rounded-lg text-xs space-y-1">
                          <p className="font-semibold text-slate-700 dark:text-slate-300">
                            Factor Details:
                          </p>
                          <div className="grid grid-cols-2 gap-2 text-slate-600 dark:text-slate-400">
                            {Object.entries(s.factors).map(([k, v]) => (
                              <div key={k} className="flex justify-between">
                                <span className="capitalize">{k.replace(/_/g, ' ')}:</span>
                                <span className="font-semibold text-slate-900 dark:text-slate-200">
                                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No Score History"
                  description="No historical revisions recorded for this lead yet."
                />
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
