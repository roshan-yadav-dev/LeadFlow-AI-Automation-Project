import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { automationService } from '../../services/automation';
import { authService } from '../../services/auth';
import { gmailService } from '../../services/gmail';
import {
  Settings,
  Server,
  Database,
  Clock,
  Shield,
  Mail,
  Cpu,
  RefreshCw,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { StatusBadge } from '../../components/common/StatusBadge';
import { LoadingSkeleton } from '../../components/common/LoadingSkeleton';
import { GmailConnectionCard } from '../../components/gmail/GmailConnectionCard';

export const SettingsPage: React.FC = () => {
  const {
    data: health,
    isLoading: healthLoading,
    refetch: refetchHealth,
    isRefetching: healthRefetching,
  } = useQuery({
    queryKey: ['worker-health'],
    queryFn: () => automationService.getHealth(),
    refetchInterval: 30000,
  });

  const { data: authStatus } = useQuery({
    queryKey: ['auth-me'],
    queryFn: () => authService.getMe(),
  });

  const { data: gmailOverview } = useQuery({
    queryKey: ['gmail-overview'],
    queryFn: () => gmailService.getOverview(),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2.5">
            <Settings className="w-7 h-7 text-primary-500" />
            System & Engine Configuration
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Backend runtime parameters, single-process automation worker diagnostics, and integration settings.
          </p>
        </div>
        <button
          onClick={() => refetchHealth()}
          disabled={healthRefetching}
          className="inline-flex items-center px-4 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition shadow-sm"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${healthRefetching ? 'animate-spin text-primary-500' : ''}`} />
          Refresh Diagnostics
        </button>
      </div>

      {/* Grid of system info */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Worker Runtime Health */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700/60 mb-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400">
                <Cpu className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white text-sm">Automation Worker</h3>
                <p className="text-xs text-slate-500">In-process event loop</p>
              </div>
            </div>
            {healthLoading ? (
              <span className="text-xs text-slate-400">Checking...</span>
            ) : health?.status === 'ok' ? (
              <StatusBadge status="ACTIVE" size="sm" />
            ) : (
              <StatusBadge status="FAILED" size="sm" />
            )}
          </div>

          {healthLoading ? (
            <LoadingSkeleton lines={4} />
          ) : (
            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
                <span className="text-slate-500 dark:text-slate-400">Worker Loop State:</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">
                  {health?.worker_running ? 'RUNNING' : 'STOPPED'}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
                <span className="text-slate-500 dark:text-slate-400">Database Engine:</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">
                  {health?.database || 'sqlite'}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
                <span className="text-slate-500 dark:text-slate-400">Thread Safety:</span>
                <span className="font-medium text-emerald-600 dark:text-emerald-400">Single Worker Guarded</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-500 dark:text-slate-400">Poll Interval:</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">10 seconds</span>
              </div>
            </div>
          )}
        </div>

        {/* Database & Storage */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700/60 mb-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400">
                <Database className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white text-sm">Storage Engine</h3>
                <p className="text-xs text-slate-500">Persistent SQLite Store</p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300">
              OPERATIONAL
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Automation DB:</span>
              <span className="font-mono text-slate-800 dark:text-slate-200 truncate max-w-[170px]" title="credentials/automation.sqlite3">
                credentials/automation.sqlite3
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Intelligence DB:</span>
              <span className="font-mono text-slate-800 dark:text-slate-200 truncate max-w-[170px]" title="credentials/gmail_intelligence.sqlite3">
                credentials/gmail_intelligence.sqlite3
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Journal Mode:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">WAL (Write-Ahead Logging)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500 dark:text-slate-400">Foreign Keys:</span>
              <span className="font-medium text-emerald-600 dark:text-emerald-400">Enforced</span>
            </div>
          </div>
        </div>

        {/* Security & Access */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700/60 mb-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white text-sm">Security & Access</h3>
                <p className="text-xs text-slate-500">Session & CSRF Layer</p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300">
              PROTECTED
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Active User:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                {authStatus?.user?.username || 'Operator'}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Session Cookie:</span>
              <span className="font-mono text-slate-800 dark:text-slate-200">leadflow_session (HttpOnly)</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">CSRF Guard:</span>
              <span className="font-medium text-emerald-600 dark:text-emerald-400">Double-Submit Enforced</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500 dark:text-slate-400">Rate Limiter:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">5 attempts / 15m window</span>
            </div>
          </div>
        </div>

        {/* Timezone & Localization */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700/60 mb-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-lg bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                <Clock className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white text-sm">Timezone & Locale</h3>
                <p className="text-xs text-slate-500">Scheduler & Display Time</p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300">
              IST (UTC+05:30)
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Default Timezone:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">Asia/Kolkata</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Scheduler Epoch:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">ISO-8601 UTC Normalized</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500 dark:text-slate-400">Frontend Presentation:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">Indian Standard Time (IST)</span>
            </div>
          </div>
        </div>

        {/* AI Model & Providers */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700/60 mb-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-lg bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400">
                <Server className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white text-sm">AI Orchestration</h3>
                <p className="text-xs text-slate-500">Groq LLM Acceleration</p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300">
              GROQ
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Primary Model:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">llama-3.3-70b-versatile</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Scoring Engine:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">LeadScoringEngine v1.0</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500 dark:text-slate-400">Deterministic Factors:</span>
              <span className="font-medium text-emerald-600 dark:text-emerald-400">Active</span>
            </div>
          </div>
        </div>

        {/* External CRM & Gmail */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700/60 mb-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-lg bg-rose-50 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400">
                <Mail className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white text-sm">CRM & Channels</h3>
                <p className="text-xs text-slate-500">Sheets & Gmail</p>
              </div>
            </div>
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
              SYNCED
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">CRM Backend:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">Google Sheets v4</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-700/40">
              <span className="text-slate-500 dark:text-slate-400">Synced Gmail Messages:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                {gmailOverview?.total_synchronized_messages ?? 'Available'}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-500 dark:text-slate-400">Matched Messages:</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                {gmailOverview?.matched_messages ?? 'Available'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Gmail Outreach & OAuth Connection Card */}
      <GmailConnectionCard />

      {/* Safety & Architecture Principles Card */}
      <div className="bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 rounded-xl p-6">
        <h3 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2 mb-3">
          <Info className="w-5 h-5 text-primary-500" />
          LeadFlow AI Operational Principles
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-slate-600 dark:text-slate-300">
          <div className="flex items-start space-x-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong className="text-slate-800 dark:text-slate-200">Strict Human Approval Safety:</strong> Approving an action
              authorizes execution but does NOT execute it directly from the browser. Customer communications are never dispatched client-side.
            </div>
          </div>
          <div className="flex items-start space-x-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong className="text-slate-800 dark:text-slate-200">Backend Source of Truth:</strong> AI scoring, rule evaluations,
              and job processing are executed on the server. Frontend never computes scores or alters database states directly.
            </div>
          </div>
          <div className="flex items-start space-x-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong className="text-slate-800 dark:text-slate-200">Deterministic Enums & Validation:</strong> All tasks,
              reminders, and workflows conform to backend Pydantic models with Asia/Kolkata timezone normalization.
            </div>
          </div>
          <div className="flex items-start space-x-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
            <div>
              <strong className="text-slate-800 dark:text-slate-200">Credential Isolation:</strong> Webhook secrets, service account keys,
              and AI tokens are stored exclusively on the server and are never exposed to browser memory.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
