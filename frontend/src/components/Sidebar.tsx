import React from 'react';
import { NavLink } from 'react-router-dom';
import { MessageSquare, Files, Plus, Trash2, History } from 'lucide-react';
import { Conversation } from '../types';

interface SidebarProps {
  conversations?: Conversation[];
  activeConversationId?: string | null;
  onSelectConversation?: (id: string) => void;
  onNewConversation?: () => void;
  onDeleteConversation?: (id: string) => void;
  isChatPage?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  conversations = [],
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  isChatPage = false,
}) => {
  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/40 flex flex-col h-[calc(100vh-4rem)]">
      {/* Navigation Links */}
      <div className="p-4 space-y-1">
        <NavLink
          to="/chat"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors ${
              isActive
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`
          }
        >
          <MessageSquare className="w-4 h-4" />
          AI Assistant Chat
        </NavLink>

        <NavLink
          to="/documents"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors ${
              isActive
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`
          }
        >
          <Files className="w-4 h-4" />
          Document Library
        </NavLink>
      </div>

      {/* Chat Specific Section: Conversations List */}
      {isChatPage && (
        <div className="flex-1 flex flex-col min-h-0 border-t border-slate-800/80 mt-2">
          <div className="p-4 pb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
              <History className="w-3.5 h-3.5" />
              History
            </span>
            <button
              onClick={onNewConversation}
              className="flex items-center gap-1.5 px-2 py-1 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-indigo-400 rounded-lg transition-colors border border-slate-700/60"
            >
              <Plus className="w-3.5 h-3.5" />
              New
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
            {conversations.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500">
                No past conversations yet
              </div>
            ) : (
              conversations.map((conv) => {
                const isActive = conv.id === activeConversationId;
                return (
                  <div
                    key={conv.id}
                    onClick={() => onSelectConversation && onSelectConversation(conv.id)}
                    className={`group flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                      isActive
                        ? 'bg-slate-800 text-indigo-300 font-medium'
                        : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate pr-2">
                      <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
                      <span className="truncate">{conv.title || 'Untitled Chat'}</span>
                    </div>

                    {onDeleteConversation && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteConversation(conv.id);
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:text-rose-400 rounded transition-opacity"
                        title="Delete conversation"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </aside>
  );
};
