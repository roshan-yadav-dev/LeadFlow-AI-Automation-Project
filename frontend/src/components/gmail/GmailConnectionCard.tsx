import React, { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Mail,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  Send,
  Inbox,
  AlertTriangle,
  X,
} from 'lucide-react';

import { gmailService } from '../../services/gmail';
import { GmailStatusResponse } from '../../types/gmail';

interface GmailConnectionCardProps {
  className?: string;
  compact?: boolean;
}

export const GmailConnectionCard: React.FC<GmailConnectionCardProps> = ({
  className = '',
  compact = false,
}) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [notification, setNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const [connectError, setConnectError] = useState<string | null>(null);

  // 1. Fetch Gmail connection status
  const {
    data: gmailStatus,
    isLoading,
    isRefetching,
    refetch,
    error: statusError,
  } = useQuery<GmailStatusResponse>({
    queryKey: ['gmail', 'status'],
    queryFn: () => gmailService.getStatus(),
    refetchInterval: 60000, // Background poll every minute
  });

  // 2. Connect mutation to initiate Google OAuth 2.0 flow
  const connectMutation = useMutation({
    mutationFn: () => {
      setConnectError(null);
      // Pass the current window origin so callback returns to this frontend deployment
      const returnUrl = window.location.origin + window.location.pathname;
      return gmailService.connect(returnUrl);
    },
    onSuccess: (data) => {
      const authUrl = data.authorization_url || data.url;
      if (authUrl) {
        // Redirect browser to Google's consent screen
        window.location.href = authUrl;
      } else {
        setConnectError('Backend did not return an authorization URL.');
      }
    },
    onError: (err: any) => {
      const msg = err.displayMessage || err.message || 'Failed to initiate Gmail authorization';
      setConnectError(msg);
    },
  });

  // 3. Process URL callback parameters upon return from Google authorization
  useEffect(() => {
    const callbackStatus = searchParams.get('gmail_status');
    const callbackError = searchParams.get('gmail_error');

    if (callbackStatus === 'connected') {
      setNotification({
        type: 'success',
        message: 'Gmail account successfully connected! Outbound email delivery and CRM sync are now authorized.',
      });
      queryClient.invalidateQueries({ queryKey: ['gmail', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      refetch();

      // Clean query params from URL without page reload
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('gmail_status');
      newParams.delete('gmail_error');
      setSearchParams(newParams, { replace: true });
    } else if (callbackStatus === 'error' || callbackError) {
      setNotification({
        type: 'error',
        message: callbackError
          ? `Google authorization was not completed (${callbackError}). Please verify your redirect URI in Google Cloud Console and try again.`
          : 'Google authorization failed or was cancelled.',
      });

      const newParams = new URLSearchParams(searchParams);
      newParams.delete('gmail_status');
      newParams.delete('gmail_error');
      setSearchParams(newParams, { replace: true });
    }
  }, [searchParams, queryClient, refetch, setSearchParams]);

  const isConnected = !!gmailStatus?.connected;

  return (
    <div
      className={`bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/80 shadow-sm overflow-hidden ${className}`}
    >
      {/* Toast Notification Banner (Success or Error) */}
      {notification && (
        <div
          className={`flex items-center justify-between px-5 py-3 text-xs font-medium border-b ${
            notification.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-200 dark:border-emerald-800/50'
              : 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-950/60 dark:text-rose-200 dark:border-rose-800/50'
          }`}
        >
          <div className="flex items-center gap-2">
            {notification.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0" />
            )}
            <span>{notification.message}</span>
          </div>
          <button
            onClick={() => setNotification(null)}
            className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/10 transition"
            title="Dismiss notice"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Initiation Error Banner */}
      {connectError && (
        <div className="flex items-center justify-between px-5 py-3 text-xs bg-rose-50 text-rose-800 border-b border-rose-200 dark:bg-rose-950/60 dark:text-rose-200 dark:border-rose-800/50">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0" />
            <span>Connection Error: {connectError}</span>
          </div>
          <button
            onClick={() => setConnectError(null)}
            className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/10 transition"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Main Card Content */}
      <div className="p-5 md:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-slate-700/60">
          {/* Title & Icon */}
          <div className="flex items-center gap-3">
            <div
              className={`p-2.5 rounded-xl flex items-center justify-center ${
                isConnected
                  ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400'
                  : 'bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400'
              }`}
            >
              <Mail className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-slate-900 dark:text-white text-base">
                  Gmail Integration & Outreach Engine
                </h3>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Official Google Workspace OAuth 2.0 channel for outbound email dispatch and CRM synchronization.
              </p>
            </div>
          </div>

          {/* Connection Status Badge */}
          <div className="flex items-center gap-2">
            {isLoading ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                <RefreshCw className="w-3 h-3 animate-spin" />
                Checking...
              </span>
            ) : isConnected ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                CONNECTED
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800">
                <AlertCircle className="w-3.5 h-3.5 text-rose-500" />
                NOT CONNECTED
              </span>
            )}
            <button
              onClick={() => refetch()}
              disabled={isRefetching}
              className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition"
              title="Refresh connection status"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Dynamic State Details & Actions */}
        <div className="pt-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          {isConnected ? (
            <>
              {/* Connected Details */}
              <div className="space-y-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-slate-500 dark:text-slate-400">Authorized Sender:</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200 bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded">
                    {gmailStatus.sender || 'Primary Workspace Account'}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-slate-600 dark:text-slate-300">
                  <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                    <ShieldCheck className="w-3.5 h-3.5" /> Outbound Dispatch Authorized
                  </span>
                  <span className="text-slate-300 dark:text-slate-600">•</span>
                  <span className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400">
                    <Inbox className="w-3.5 h-3.5" /> Inbound Intelligence Active
                  </span>
                </div>
              </div>

              {/* Connected Actions */}
              <div className="flex flex-wrap items-center gap-2.5">
                <button
                  onClick={() => navigate('/gmail')}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 transition"
                >
                  <Inbox className="w-3.5 h-3.5" />
                  View Inbox
                </button>
                <button
                  onClick={() => connectMutation.mutate()}
                  disabled={connectMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition"
                  title="Re-authorize with Google if credentials expire"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${connectMutation.isPending ? 'animate-spin' : ''}`} />
                  {connectMutation.isPending ? 'Redirecting...' : 'Reconnect Account'}
                </button>
              </div>
            </>
          ) : (
            <>
              {/* Disconnected Notice */}
              <div className="text-xs text-slate-600 dark:text-slate-300 max-w-xl">
                <p>
                  Gmail is currently <strong>not connected</strong>. Outbound email dispatch is safely paused. Approved email drafts will not be sent until a legitimate Google account is authorized.
                </p>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                  OAuth scopes requested: <code className="font-mono">gmail.send</code>, <code className="font-mono">gmail.readonly</code>.
                </p>
              </div>

              {/* Connect Button */}
              <div>
                <button
                  onClick={() => connectMutation.mutate()}
                  disabled={connectMutation.isPending}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-bold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition disabled:opacity-50"
                >
                  {connectMutation.isPending ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Redirecting to Google...
                    </>
                  ) : (
                    <>
                      <Mail className="w-4 h-4" />
                      Connect Gmail Account
                      <ExternalLink className="w-3 h-3 ml-0.5 opacity-70" />
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
