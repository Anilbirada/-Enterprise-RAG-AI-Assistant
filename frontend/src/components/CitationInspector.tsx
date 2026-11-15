import React from 'react';
import { Citation } from '../types';
import { X, FileText, Bookmark } from 'lucide-react';

interface CitationInspectorProps {
  citation: Citation | null;
  onClose: () => void;
}

export const CitationInspector: React.FC<CitationInspectorProps> = ({ citation, onClose }) => {
  if (!citation) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col">
          {/* Header */}
          <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-500/10 text-indigo-400 font-semibold text-sm border border-indigo-500/20">
                {citation.citation_number ?? 1}
              </span>
              <h2 className="text-base font-semibold text-slate-100">Citation Source</h2>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 transition-colors p-1.5 rounded-lg hover:bg-slate-800"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-6 flex-1 overflow-y-auto">
            {/* Metadata Card */}
            <div className="bg-slate-950/60 rounded-xl p-4 border border-slate-800/80 space-y-3">
              <div className="flex items-start gap-3">
                <FileText className="w-5 h-5 text-indigo-400 mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Document
                  </div>
                  <div className="text-sm font-semibold text-slate-100 truncate">
                    {citation.document_title}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-800/50 text-xs">
                <div>
                  <span className="text-slate-400">Page Number:</span>{' '}
                  <span className="text-slate-200 font-medium">
                    {citation.page_number !== null && citation.page_number !== undefined
                      ? `Page ${citation.page_number}`
                      : 'N/A'}
                  </span>
                </div>
                {citation.score !== undefined && (
                  <div>
                    <span className="text-slate-400">Relevance:</span>{' '}
                    <span className="text-emerald-400 font-mono font-medium">
                      {(citation.score * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Exact Text Snippet */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <Bookmark className="w-3.5 h-3.5 text-indigo-400" />
                Exact Extracted Passage
              </div>
              <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 text-sm leading-relaxed text-slate-300 font-mono text-xs whitespace-pre-wrap selection:bg-indigo-500/30">
                {citation.snippet}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500">
            <span>Verified Source Chunk</span>
            <span className="font-mono">{citation.chunk_id.slice(0, 8)}...</span>
          </div>
        </div>
      </div>
    </div>
  );
};
