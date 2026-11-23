import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import {
  Menu,
  Moon,
  Sun,
  User,
  Activity,
  Cpu,
} from 'lucide-react';

interface TopbarProps {
  onToggleMobileMenu: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
  workerRunning?: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({
  onToggleMobileMenu,
  isDark,
  onToggleTheme,
  workerRunning = true,
}) => {
  const location = useLocation();
  const { user } = useAuth();

  // Compute breadcrumbs
  const pathSegments = location.pathname.split('/').filter(Boolean);
  const title = pathSegments.length > 0
    ? pathSegments[0].replace('-', ' ').toUpperCase()
    : 'DASHBOARD';

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between h-16 px-4 md:px-8 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800">
      {/* Left: Mobile Hamburger & Page Title / Breadcrumbs */}
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleMobileMenu}
          className="md:hidden p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <nav className="flex items-center gap-2 text-xs text-slate-400 font-medium">
            <Link to="/dashboard" className="hover:text-slate-600 dark:hover:text-slate-200">
              LeadFlow
            </Link>
            {pathSegments.map((segment, index) => (
              <React.Fragment key={index}>
                <span>/</span>
                <span className="capitalize text-slate-700 dark:text-slate-300">
                  {segment.replace('-', ' ')}
                </span>
              </React.Fragment>
            ))}
          </nav>
          <h1 className="text-lg font-bold text-slate-900 dark:text-white capitalize">
            {title.toLowerCase()}
          </h1>
        </div>
      </div>

      {/* Right: Status Indicators & User Controls */}
      <div className="flex items-center gap-3">
        {/* Worker Status Badge */}
        <div
          className={`hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
            workerRunning
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300'
              : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300'
          }`}
          title={workerRunning ? 'Worker is polling queue' : 'Worker is stopped'}
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>Worker: {workerRunning ? 'Running' : 'Stopped'}</span>
        </div>

        {/* System Health */}
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300">
          <Activity className="w-3.5 h-3.5 text-indigo-500" />
          <span>System: Healthy</span>
        </div>

        {/* Theme Switcher */}
        <button
          onClick={onToggleTheme}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>

        {/* User Profile */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-200 dark:border-slate-800">
          <div className="hidden md:flex flex-col text-right">
            <span className="text-xs font-semibold text-slate-900 dark:text-white">
              {user?.username || 'Operator'}
            </span>
            <span className="text-[10px] uppercase font-bold text-slate-400">
              {user?.role || 'Admin'}
            </span>
          </div>

          <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-950 flex items-center justify-center text-indigo-700 dark:text-indigo-300 font-bold text-xs border border-indigo-200 dark:border-indigo-800">
            <User className="w-4 h-4" />
          </div>
        </div>
      </div>
    </header>
  );
};
