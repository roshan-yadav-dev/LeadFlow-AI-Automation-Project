import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search,
  Plus,
  RefreshCw,
  Eye,
  Calculator,
  Building,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';

import { leadsService } from '../../services/leads';
import { scoringService } from '../../services/scoring';
import { StatusBadge } from '../../components/common/StatusBadge';
import { ScoreGauge } from '../../components/common/ScoreGauge';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { TableSkeleton } from '../../components/common/LoadingSkeleton';
import { EmptyState } from '../../components/common/EmptyState';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { NewLeadModal } from './NewLeadModal';

export const LeadsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const tierFilter = searchParams.get('tier') || '';
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [isNewLeadOpen, setIsNewLeadOpen] = useState(false);
  const [calculatingLeadId, setCalculatingLeadId] = useState<string | null>(null);

  // Fetch leads
  const {
    data,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['leads', { search, status: statusFilter, tier: tierFilter, sortBy, sortOrder, page }],
    queryFn: () =>
      leadsService.listLeads({
        search: search || undefined,
        status: statusFilter || undefined,
        tier: tierFilter || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: pageSize,
      }),
  });

  // Calculate score mutation
  const calculateScoreMutation = useMutation({
    mutationFn: (leadId: string) => scoringService.calculateScore(leadId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setCalculatingLeadId(null);
    },
    onError: () => {
      setCalculatingLeadId(null);
    },
  });

  const handleCalculateScore = (e: React.MouseEvent, leadId: string) => {
    e.stopPropagation();
    setCalculatingLeadId(leadId);
    calculateScoreMutation.mutate(leadId);
  };

  const handleTierChange = (tier: string) => {
    if (tier) {
      searchParams.set('tier', tier);
    } else {
      searchParams.delete('tier');
    }
    setSearchParams(searchParams);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header & CRM Sync Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              Lead Management
            </h2>
            {data && (
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                  data.crm_synced
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-amber-50 text-amber-700 border-amber-200'
                }`}
                title={
                  data.crm_synced
                    ? 'Synchronized with Google Sheets CRM'
                    : 'Using local offline intelligence storage'
                }
              >
                {data.crm_synced ? (
                  <>
                    <CheckCircle className="w-3.5 h-3.5" />
                    <span>CRM Synced</span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Local Cache</span>
                  </>
                )}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Capture, track, score, and manage inbound leads across communication channels.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
            title="Refresh Leads"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setIsNewLeadOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            Add Inbound Lead
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by name, email, company..."
              className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* Temperature Tier Filter */}
          <div>
            <select
              value={tierFilter}
              onChange={(e) => handleTierChange(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 font-medium"
            >
              <option value="">All Temperatures (HOT, WARM, COLD)</option>
              <option value="HOT">HOT Leads (&ge; 70)</option>
              <option value="WARM">WARM Leads (40-69)</option>
              <option value="COLD">COLD Leads (&lt; 40)</option>
            </select>
          </div>

          {/* Status Filter */}
          <div>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 font-medium"
            >
              <option value="">All Lead Statuses</option>
              <option value="NEW">NEW</option>
              <option value="CONTACTED">CONTACTED</option>
              <option value="QUALIFIED">QUALIFIED</option>
              <option value="NEGOTIATING">NEGOTIATING</option>
              <option value="CLOSED">CLOSED</option>
            </select>
          </div>

          {/* Sort By */}
          <div className="flex gap-2">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="flex-1 px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 focus:ring-2 focus:ring-indigo-500 font-medium"
            >
              <option value="created_at">Sort: Created Date</option>
              <option value="score">Sort: Lead Score</option>
              <option value="name">Sort: Name</option>
              <option value="company">Sort: Company</option>
            </select>
            <button
              onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              className="px-3 py-2 text-xs font-bold border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition uppercase"
              title="Toggle sort direction"
            >
              {sortOrder}
            </button>
          </div>
        </div>
      </div>

      {/* Leads Table */}
      {isLoading ? (
        <TableSkeleton rows={8} columns={9} />
      ) : error ? (
        <ErrorBanner
          message={(error as Error).message || 'Failed to load leads'}
          onRetry={() => refetch()}
        />
      ) : !data || data.leads.length === 0 ? (
        <EmptyState
          title="No Leads Found"
          description={
            search || tierFilter || statusFilter
              ? 'No leads match your active filters. Try resetting the search or filter settings.'
              : 'You have not captured any inbound leads yet. Add your first lead to get started.'
          }
          action={{
            label: 'Add Inbound Lead',
            onClick: () => setIsNewLeadOpen(true),
          }}
        />
      ) : (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-4 py-3.5">Name</th>
                  <th className="px-4 py-3.5">Email</th>
                  <th className="px-4 py-3.5">Company</th>
                  <th className="px-4 py-3.5">Lead Score</th>
                  <th className="px-4 py-3.5">Temperature</th>
                  <th className="px-4 py-3.5">Intent</th>
                  <th className="px-4 py-3.5">Last Interaction</th>
                  <th className="px-4 py-3.5">Created Date</th>
                  <th className="px-4 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/60">
                {data.leads.map((lead) => (
                  <tr
                    key={lead.lead_id}
                    onClick={() => navigate(`/leads/${lead.lead_id}`)}
                    className="hover:bg-slate-50/80 dark:hover:bg-slate-750/50 transition cursor-pointer group"
                  >
                    <td className="px-4 py-3.5 font-semibold text-slate-900 dark:text-white">
                      <div className="flex flex-col">
                        <span>{lead.name || 'Anonymous Lead'}</span>
                        <span className="text-[10px] text-slate-400 font-mono font-normal">
                          {lead.lead_id}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs">{lead.email || '—'}</td>
                    <td className="px-4 py-3.5">
                      {lead.company ? (
                        <div className="flex items-center gap-1.5">
                          <Building className="w-3.5 h-3.5 text-slate-400" />
                          <span>{lead.company}</span>
                        </div>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <ScoreGauge score={lead.score} size="md" />
                    </td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={lead.tier} variant="tier" />
                    </td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={lead.intent} />
                    </td>
                    <td className="px-4 py-3.5">
                      <DateTimeDisplay isoString={lead.last_interaction} />
                    </td>
                    <td className="px-4 py-3.5">
                      <DateTimeDisplay isoString={lead.created_at} includeTime={false} />
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => handleCalculateScore(e, lead.lead_id)}
                          disabled={calculatingLeadId === lead.lead_id}
                          className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 text-slate-600 hover:text-indigo-600 transition"
                          title="Calculate Score via AI Scoring Engine"
                        >
                          <Calculator className={`w-4 h-4 ${calculatingLeadId === lead.lead_id ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/leads/${lead.lead_id}`);
                          }}
                          className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 transition"
                          title="View Full Profile"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-6 py-3.5 border-t border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-xs text-slate-500">
            <span>
              Showing {data.leads.length} of {data.total} leads
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="font-semibold text-slate-700 dark:text-slate-300">
                Page {page} of {Math.max(1, Math.ceil(data.total / pageSize))}
              </span>
              <button
                disabled={page >= Math.ceil(data.total / pageSize)}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Lead Modal */}
      <NewLeadModal
        isOpen={isNewLeadOpen}
        onClose={() => setIsNewLeadOpen(false)}
        onLeadCreated={() => {
          queryClient.invalidateQueries({ queryKey: ['leads'] });
          queryClient.invalidateQueries({ queryKey: ['dashboard'] });
        }}
      />
    </div>
  );
};
