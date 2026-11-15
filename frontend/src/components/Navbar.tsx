import React from 'react';
import { useAuth } from '../context/AuthContext';
import { Building2, LogOut, Shield, User as UserIcon, Bot } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { user, organization, logout } = useAuth();

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-40">
      {/* Brand & Organization Context */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
              Enterprise RAG <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-mono">v1.0</span>
            </h1>
          </div>
        </div>

        {organization && (
          <div className="hidden md:flex items-center gap-2 pl-4 border-l border-slate-800 text-xs">
            <Building2 className="w-4 h-4 text-slate-400" />
            <span className="font-semibold text-slate-200">{organization.name}</span>
            <span className="text-slate-500 font-mono">({organization.slug})</span>
          </div>
        )}
      </div>

      {/* User info & Actions */}
      <div className="flex items-center gap-4">
        {user && (
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex flex-col text-right">
              <span className="text-xs font-medium text-slate-200">
                {user.full_name || user.email}
              </span>
              <div className="flex items-center justify-end gap-1.5">
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold tracking-wider uppercase px-1.5 py-0.5 rounded bg-slate-800 text-indigo-400 border border-slate-700">
                  <Shield className="w-2.5 h-2.5" />
                  {user.role}
                </span>
              </div>
            </div>

            <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
              <UserIcon className="w-4 h-4" />
            </div>

            <button
              onClick={() => logout()}
              title="Sign Out"
              className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
