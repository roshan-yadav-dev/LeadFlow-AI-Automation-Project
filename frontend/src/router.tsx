import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';

import { AppLayout } from './components/layout/AppLayout';
import { LoginPage } from './pages/Login/LoginPage';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { LeadsPage } from './pages/Leads/LeadsPage';
import { LeadDetailPage } from './pages/Leads/LeadDetailPage';
import { LeadScoringPage } from './pages/LeadScoring/LeadScoringPage';
import { TasksPage } from './pages/Tasks/TasksPage';
import { RemindersPage } from './pages/Reminders/RemindersPage';
import { WorkflowsPage } from './pages/Workflows/WorkflowsPage';
import { ApprovalsPage } from './pages/Approvals/ApprovalsPage';
import { GmailPage } from './pages/GmailIntelligence/GmailPage';
import { JobsPage } from './pages/AutomationJobs/JobsPage';
import { AuditLogsPage } from './pages/AuditLogs/AuditLogsPage';
import { SettingsPage } from './pages/Settings/SettingsPage';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-10 h-10 border-3 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm font-medium text-slate-400">Verifying session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Protected App Routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="leads" element={<LeadsPage />} />
        <Route path="leads/:id" element={<LeadDetailPage />} />
        <Route path="lead-scoring" element={<LeadScoringPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="reminders" element={<RemindersPage />} />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        <Route path="gmail" element={<GmailPage />} />
        <Route path="automation-jobs" element={<JobsPage />} />
        <Route path="audit-logs" element={<AuditLogsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      {/* Catch-all 404 */}
      <Route
        path="*"
        element={
          <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center p-6 text-center">
            <h1 className="text-6xl font-extrabold text-primary-500 mb-2">404</h1>
            <h2 className="text-2xl font-bold text-white mb-2">Page Not Found</h2>
            <p className="text-slate-400 text-sm max-w-md mb-6">
              The page you requested does not exist or may have been relocated.
            </p>
            <a
              href="/dashboard"
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition"
            >
              Return to Dashboard
            </a>
          </div>
        }
      />
    </Routes>
  );
};
