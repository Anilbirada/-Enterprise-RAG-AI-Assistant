import React from 'react';
import { DocumentStatus } from '../types';
import { Loader2, CheckCircle2, AlertCircle, Clock } from 'lucide-react';

interface StatusBadgeProps {
  status: DocumentStatus;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  switch (status) {
    case 'COMPLETED':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 ${className}`}
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          Completed
        </span>
      );
    case 'FAILED':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20 ${className}`}
        >
          <AlertCircle className="w-3.5 h-3.5" />
          Failed
        </span>
      );
    case 'PARSING':
    case 'CHUNKING':
    case 'EMBEDDING':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20 ${className}`}
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          {status.charAt(0) + status.slice(1).toLowerCase()}
        </span>
      );
    case 'UPLOADED':
    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-300 border border-slate-500/20 ${className}`}
        >
          <Clock className="w-3.5 h-3.5" />
          Uploaded
        </span>
      );
  }
};
