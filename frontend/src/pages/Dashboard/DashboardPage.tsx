import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Flame,
  Sun,
  Snowflake,
  CheckSquare,
  AlertTriangle,
  Bell,
  ShieldCheck,
  GitBranch,
  PlayCircle,
  Activity,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  CartesianGrid,
} from 'recharts';

import { dashboardService } from '../../services/dashboard';
import { StatCard } from '../../components/common/StatCard';
import { TableSkeleton, CardSkeleton } from '../../components/common/LoadingSkeleton';
import { ErrorBanner } from '../../components/common/ErrorBanner';
import { EmptyState } from '../../components/common/EmptyState';
import { DateTimeDisplay } from '../../components/common/DateTimeDisplay';
import { StatusBadge } from '../../components/common/StatusBadge';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();

  const {
    data: overview,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: () => dashboardService.getOverview(),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <TableSkeleton rows={6} />
      </div>
    );
  }

  if (error || !overview) {
    return (
      <ErrorBanner
        message={error ? (error as Error).message : 'Unable to load dashboard data'}
        onRetry={() => refetch()}
      />
    );
  }

  const hasScoreData = overview?.score_distribution?.some((d) => d.value > 0) ?? false;
  const hasTempData = overview?.temperature_distribution?.some((d) => d.value > 0) ?? false;
  const hasTaskData = overview?.task_status_distribution?.some((d) => d.value > 0) ?? false;
  const hasExecData = overview?.workflow_execution_distribution?.some((d) => d.value > 0) ?? false;
  const hasTrendData = (overview?.lead_creation_trend && overview.lead_creation_trend.length > 0) ?? false;

  return (
    <div className="space-y-6">
      {/* Top Stat Cards: Row 1 */}
      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard
          title="Total Leads"
          value={overview.total_leads}
          icon={Users}
          color="indigo"
          onClick={() => navigate('/leads')}
        />
        <StatCard
          title="Hot Leads"
          value={overview.hot_leads}
          subtitle="Score >= 70"
          icon={Flame}
          color="rose"
          onClick={() => navigate('/leads?tier=HOT')}
        />
        <StatCard
          title="Warm Leads"
          value={overview.warm_leads}
          subtitle="Score 40-69"
          icon={Sun}
          color="amber"
          onClick={() => navigate('/leads?tier=WARM')}
        />
        <StatCard
          title="Cold Leads"
          value={overview.cold_leads}
          subtitle="Score < 40"
          icon={Snowflake}
          color="blue"
          onClick={() => navigate('/leads?tier=COLD')}
        />
        <StatCard
          title="Pending Approvals"
          value={overview.pending_approvals}
          subtitle="Requires human signoff"
          icon={ShieldCheck}
          color="rose"
          onClick={() => navigate('/approvals')}
        />
      </div>

      {/* Stat Cards: Row 2 */}
      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard
          title="Upcoming Tasks"
          value={overview.pending_followups}
          icon={CheckSquare}
          color="indigo"
          onClick={() => navigate('/tasks')}
        />
        <StatCard
          title="Overdue Tasks"
          value={overview.overdue_followups}
          subtitle="Needs attention"
          icon={AlertTriangle}
          color="rose"
          onClick={() => navigate('/tasks?tab=overdue')}
        />
        <StatCard
          title="Pending Reminders"
          value={overview.pending_reminders}
          icon={Bell}
          color="amber"
          onClick={() => navigate('/reminders')}
        />
        <StatCard
          title="Active Workflows"
          value={overview.active_workflows}
          icon={GitBranch}
          color="indigo"
          onClick={() => navigate('/workflows')}
        />
        <StatCard
          title="Workflow Executions"
          value={overview.total_executions}
          icon={PlayCircle}
          color="slate"
          onClick={() => navigate('/workflows?tab=executions')}
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 1. Temperature Distribution */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Lead Temperature Distribution
            </h3>
            <span className="text-xs text-slate-400 font-medium">HOT / WARM / COLD</span>
          </div>
          {hasTempData ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={overview.temperature_distribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {overview.temperature_distribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color || '#6366f1'} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="No Temperature Data"
              description="Calculate scores for your leads to view the temperature distribution."
            />
          )}
        </div>

        {/* 2. Score Distribution */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Lead Score Distribution
            </h3>
            <span className="text-xs text-slate-400 font-medium">0 - 100 Points</span>
          </div>
          {hasScoreData ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={overview.score_distribution}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="name" fontSize={11} stroke="#94a3b8" />
                  <YAxis fontSize={11} stroke="#94a3b8" allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="No Scores Available"
              description="Recalculate or record lead scores to generate distribution statistics."
            />
          )}
        </div>

        {/* 3. Follow-up Task Status */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Follow-Up Task Breakdown
            </h3>
            <span className="text-xs text-slate-400 font-medium">By Status</span>
          </div>
          {hasTaskData ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={overview.task_status_distribution}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="name" fontSize={11} stroke="#94a3b8" />
                  <YAxis fontSize={11} stroke="#94a3b8" allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {overview.task_status_distribution.map((entry, index) => (
                      <Cell key={`task-cell-${index}`} fill={entry.color || '#3b82f6'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="No Follow-Up Tasks"
              description="Schedule follow-up tasks to view status progress and completion rates."
            />
          )}
        </div>

        {/* 4. Lead Creation Trend / Executions */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Lead Ingestion & Growth Trend
            </h3>
            <span className="text-xs text-slate-400 font-medium">Historical Activity</span>
          </div>
          {hasTrendData ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={overview.lead_creation_trend}>
                  <defs>
                    <linearGradient id="leadGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="date" fontSize={11} stroke="#94a3b8" />
                  <YAxis fontSize={11} stroke="#94a3b8" allowDecimals={false} />
                  <Tooltip />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#4f46e5"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#leadGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              title="No Trend Data Available"
              description="Historical creation dates are not yet available to plot an ingestion trend."
            />
          )}
        </div>
      </div>

      {/* Recent Automation Activity */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50">
          <div className="flex items-center gap-2.5">
            <Activity className="w-5 h-5 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Recent Automation & System Activity
            </h3>
          </div>
          <button
            onClick={() => navigate('/audit-logs')}
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 transition"
          >
            View Full Audit Trail &rarr;
          </button>
        </div>

        {overview.recent_activity.length > 0 ? (
          <div className="divide-y divide-slate-100 dark:divide-slate-700/50">
            {overview.recent_activity.slice(0, 8).map((act, index) => (
              <div key={index} className="flex items-center justify-between px-6 py-3.5 text-sm">
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-indigo-500" />
                  <div>
                    <span className="font-semibold text-slate-900 dark:text-white">
                      {act.action}
                    </span>
                    <span className="text-slate-500 dark:text-slate-400 text-xs ml-2">
                      ({act.entity_type} {act.entity_id})
                    </span>
                    {act.lead_id && (
                      <span className="text-indigo-600 dark:text-indigo-400 text-xs font-medium ml-2">
                        Lead: {act.lead_id}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <span className="text-xs text-slate-400 uppercase font-semibold">
                    By {act.actor}
                  </span>
                  <DateTimeDisplay isoString={act.timestamp} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-8">
            <EmptyState
              title="No Recent Activity"
              description="System audit logs and automation events will be displayed here."
            />
          </div>
        )}
      </div>
    </div>
  );
};
