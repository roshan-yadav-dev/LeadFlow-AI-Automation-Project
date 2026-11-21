import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Award,
  CheckSquare,
  Bell,
  GitBranch,
  ShieldCheck,
  Mail,
  Cpu,
  FileText,
  Settings,
  Sparkles,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  pendingApprovalsCount?: number;
  overdueTasksCount?: number;
}

const navItems = [
  { name: 'Overview', to: '/dashboard', icon: LayoutDashboard },
  { name: 'Leads', to: '/leads', icon: Users },
  { name: 'Lead Scoring', to: '/scoring', icon: Award },
  { name: 'Tasks', to: '/tasks', icon: CheckSquare, badgeKey: 'tasks' },
  { name: 'Reminders', to: '/reminders', icon: Bell },
  { name: 'Workflows', to: '/workflows', icon: GitBranch },
  { name: 'Approvals', to: '/approvals', icon: ShieldCheck, badgeKey: 'approvals' },
  { name: 'Gmail Intelligence', to: '/gmail', icon: Mail },
  { name: 'Automation Jobs', to: '/jobs', icon: Cpu },
  { name: 'Audit Logs', to: '/audit-logs', icon: FileText },
  { name: 'Settings', to: '/settings', icon: Settings },
];

export const Sidebar: React.FC<SidebarProps> = ({
  isCollapsed,
  onToggleCollapse,
  pendingApprovalsCount = 0,
  overdueTasksCount = 0,
}) => {
  return (
    <aside
      className={`relative flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-300 z-30 ${
        isCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-slate-200 dark:border-slate-800">
        {!isCollapsed && (
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div className="flex flex-col">
              <span className="text-base font-bold text-slate-900 dark:text-white tracking-tight">
                LeadFlow <span className="text-indigo-600">AI</span>
              </span>
              <span className="text-[10px] text-slate-400 font-semibold tracking-wider uppercase">
                Enterprise CRM
              </span>
            </div>
          </div>
        )}
        {isCollapsed && (
          <div className="mx-auto p-2 rounded-xl bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          className="hidden md:flex p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          let badge = 0;
          let badgeColor = 'bg-slate-100 text-slate-600';
          if (item.badgeKey === 'approvals' && pendingApprovalsCount > 0) {
            badge = pendingApprovalsCount;
            badgeColor = 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
          } else if (item.badgeKey === 'tasks' && overdueTasksCount > 0) {
            badge = overdueTasksCount;
            badgeColor = 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300';
          }

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl font-medium text-sm transition group ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300 font-semibold'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100/70 dark:hover:bg-slate-800/60'
                }`
              }
              title={isCollapsed ? item.name : undefined}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              {!isCollapsed && <span className="flex-1 truncate">{item.name}</span>}
              {!isCollapsed && badge > 0 && (
                <span
                  className={`px-2 py-0.5 text-xs font-bold rounded-full ${badgeColor}`}
                >
                  {badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Footer / System Status */}
      <div className="p-3 border-t border-slate-200 dark:border-slate-800">
        {!isCollapsed ? (
          <div className="flex items-center justify-between px-2 py-1 text-xs text-slate-500 dark:text-slate-400">
            <span>Version 1.0.0</span>
            <span className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Active
            </span>
          </div>
        ) : (
          <div className="flex justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        )}
      </div>
    </aside>
  );
};
