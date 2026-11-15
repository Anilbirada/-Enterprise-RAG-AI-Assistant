import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../lib/api';
import { Conversation, Message, Citation, SearchMode } from '../types';
import { Sidebar } from '../components/Sidebar';
import { CitationInspector } from '../components/CitationInspector';
import {
  Send,
  Bot,
  User as UserIcon,
  Sparkles,
  Bookmark,
  Layers,
  Search,
} from 'lucide-react';

export const ChatPage: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  // Retrieval mode settings
  const [searchMode, setSearchMode] = useState<SearchMode>('hybrid');

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch conversations on load
  const loadConversations = async () => {
    try {
      const data = await api.getConversations();
      setConversations(data);
      if (data.length > 0 && !activeConvId) {
        setActiveConvId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  };

  useEffect(() => {
    loadConversations();
  }, []);

  // Fetch messages when active conversation changes
  useEffect(() => {
    if (!activeConvId) {
      setMessages([]);
      return;
    }

    const fetchMessages = async () => {
      try {
        const conv = await api.getConversation(activeConvId);
        setMessages(conv.messages || []);
      } catch (err) {
        console.error('Failed to load messages for conversation:', err);
      }
    };

    fetchMessages();
  }, [activeConvId]);

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation('New Chat');
      setConversations([newConv, ...conversations]);
      setActiveConvId(newConv.id);
      setMessages([]);
    } catch (err) {
      console.error('Failed to create new conversation:', err);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isStreaming) return;

    const userPrompt = inputQuery.trim();
    setInputQuery('');

    // Generate local user message
    const userMsg: Message = {
      id: `local-user-${Date.now()}`,
      conversation_id: activeConvId || '',
      role: 'user',
      content: userPrompt,
      created_at: new Date().toISOString(),
    };

    // Temporary placeholder for assistant streaming message
    const assistantMsgId = `local-assistant-${Date.now()}`;
    const initialAssistantMsg: Message = {
      id: assistantMsgId,
      conversation_id: activeConvId || '',
      role: 'assistant',
      content: '',
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
    setIsStreaming(true);

    let accumulatedContent = '';
    let accumulatedCitations: Citation[] = [];

    await api.streamChatCompletion(
      {
        conversation_id: activeConvId || undefined,
        message: userPrompt,
        search_mode: searchMode,
        stream: true,
      },
      {
        onToken: (token: string) => {
          accumulatedContent += token;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, content: accumulatedContent } : msg
            )
          );
        },
        onCitations: (citations: Citation[]) => {
          accumulatedCitations = citations;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, citations: accumulatedCitations } : msg
            )
          );
        },
        onDone: (data) => {
          if (!activeConvId && data.conversation_id) {
            setActiveConvId(data.conversation_id);
            loadConversations();
          }
          setIsStreaming(false);
        },
        onError: (err) => {
          console.error('Streaming error:', err);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? {
                    ...msg,
                    content:
                      accumulatedContent ||
                      `*Error generating response: ${err.message}. Please try again.*`,
                  }
                : msg
            )
          );
          setIsStreaming(false);
        },
      }
    );
  };

  // Render citation badges inside markdown or as pill attachments
  const renderMessageContent = (msg: Message) => {
    if (msg.role === 'user') {
      return <div className="text-sm text-slate-100 whitespace-pre-wrap">{msg.content}</div>;
    }

    // Replace [1], [2], etc. in content or render Markdown
    return (
      <div className="space-y-3">
        <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-slate-950 prose-pre:border prose-pre:border-slate-800">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Custom renderer for text to highlight bracket citations [1], [2]
              p: ({ children }) => {
                const processNodes = (nodes: React.ReactNode): React.ReactNode => {
                  return React.Children.map(nodes, (node) => {
                    if (typeof node === 'string') {
                      const regex = /\[(\d+)\]/g;
                      const parts: React.ReactNode[] = [];
                      let lastIndex = 0;
                      let match: RegExpExecArray | null;

                      while ((match = regex.exec(node)) !== null) {
                        const citationNum = parseInt(match[1], 10);
                        if (match.index > lastIndex) {
                          parts.push(node.substring(lastIndex, match.index));
                        }
                        const matchedCitation = msg.citations?.find(
                          (c) => c.citation_number === citationNum
                        ) || {
                          chunk_id: '',
                          document_id: '',
                          document_title: `Source [${citationNum}]`,
                          citation_number: citationNum,
                          snippet: 'Source snippet details in references below.',
                        };

                        parts.push(
                          <button
                            key={`${match.index}-${citationNum}`}
                            onClick={() => setSelectedCitation(matchedCitation)}
                            className="inline-flex items-center justify-center px-1.5 py-0.2 rounded text-[11px] font-semibold font-mono bg-indigo-500/20 hover:bg-indigo-500/40 text-indigo-300 border border-indigo-500/30 mx-0.5 cursor-pointer transition-colors align-baseline"
                            title={`Inspect Source [${citationNum}]`}
                          >
                            [{citationNum}]
                          </button>
                        );
                        lastIndex = regex.lastIndex;
                      }

                      if (lastIndex < node.length) {
                        parts.push(node.substring(lastIndex));
                      }
                      return parts.length > 0 ? parts : node;
                    }
                    return node;
                  });
                };

                return <p>{processNodes(children)}</p>;
              },
            }}
          >
            {msg.content}
          </ReactMarkdown>
        </div>

        {/* Citations Footer Section */}
        {msg.citations && msg.citations.length > 0 && (
          <div className="pt-3 border-t border-slate-800/60 mt-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              <Bookmark className="w-3 h-3 text-indigo-400" />
              Verified Citations ({msg.citations.length})
            </div>
            <div className="flex flex-wrap gap-2">
              {msg.citations.map((c, idx) => (
                <button
                  key={c.chunk_id || idx}
                  onClick={() => setSelectedCitation(c)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700/60 transition-colors"
                >
                  <span className="w-4 h-4 rounded-full bg-indigo-500/20 text-indigo-400 flex items-center justify-center text-[10px] font-mono font-bold">
                    {c.citation_number || idx + 1}
                  </span>
                  <span className="max-w-[140px] truncate">{c.document_title}</span>
                  {c.page_number && (
                    <span className="text-[10px] text-slate-500">p.{c.page_number}</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sidebar with conversation history */}
      <Sidebar
        isChatPage={true}
        conversations={conversations}
        activeConversationId={activeConvId}
        onSelectConversation={(id) => setActiveConvId(id)}
        onNewConversation={handleNewConversation}
      />

      {/* Main Chat Thread Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-slate-950">
        {/* Chat Control Toolbar */}
        <div className="h-12 border-b border-slate-800 px-6 flex items-center justify-between bg-slate-900/40">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-400">Retrieval Mode:</span>
            <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-xs">
              <button
                onClick={() => setSearchMode('hybrid')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-colors ${
                  searchMode === 'hybrid'
                    ? 'bg-indigo-600 text-white font-medium shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                Hybrid (RRF)
              </button>
              <button
                onClick={() => setSearchMode('dense')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-colors ${
                  searchMode === 'dense'
                    ? 'bg-indigo-600 text-white font-medium shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Search className="w-3.5 h-3.5" />
                Dense Vector
              </button>
            </div>
          </div>

          <div className="text-xs text-slate-500 font-mono">
            {searchMode === 'hybrid'
              ? 'Dense (0.7) + Full-Text (0.3) with Reciprocal Rank Fusion'
              : 'Cosine Distance (text-embedding-3-small 1536d)'}
          </div>
        </div>

        {/* Message Thread Scroll Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto p-4 space-y-4">
              <div className="w-16 h-16 rounded-3xl bg-indigo-600/10 text-indigo-400 flex items-center justify-center border border-indigo-500/20 shadow-xl shadow-indigo-600/10">
                <Sparkles className="w-8 h-8" />
              </div>
              <h2 className="text-xl font-bold text-slate-100">Enterprise AI Assistant</h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Ask questions against your company documents. All answers are grounded with
                verifiable citations referencing exact document sections.
              </p>

              <div className="grid grid-cols-1 gap-2 w-full pt-4 text-left">
                {[
                  'What are the compliance policies for remote work?',
                  'Summarize the onboarding roadmap for engineering teams.',
                  'What are the key SLA commitments in our contracts?',
                ].map((sample, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setInputQuery(sample);
                    }}
                    className="p-3 text-xs bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-xl border border-slate-800/80 transition-colors text-left"
                  >
                    "{sample}"
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-4 max-w-4xl mx-auto ${
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shrink-0 shadow-md shadow-indigo-500/20 mt-1">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                )}

                <div
                  className={`rounded-2xl px-5 py-4 max-w-2xl text-sm ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20'
                      : 'bg-slate-900/80 border border-slate-800 shadow-xl'
                  }`}
                >
                  {renderMessageContent(msg)}
                </div>

                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 mt-1 text-slate-300">
                    <UserIcon className="w-4 h-4" />
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/60 backdrop-blur-md">
          <form
            onSubmit={handleSendMessage}
            className="max-w-4xl mx-auto flex items-center gap-3 relative"
          >
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder="Ask a question about your enterprise documents..."
              disabled={isStreaming}
              className="flex-1 bg-slate-950 border border-slate-800 rounded-2xl py-3.5 pl-5 pr-14 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition-all shadow-inner"
            />
            <button
              type="submit"
              disabled={!inputQuery.trim() || isStreaming}
              className="absolute right-2.5 top-2.5 p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 disabled:hover:bg-indigo-600 text-white rounded-xl shadow-md shadow-indigo-600/30 transition-all"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <div className="text-center text-[11px] text-slate-500 mt-2">
            Responses are strictly grounded on retrieved source chunks. Citations can be verified
            interactively.
          </div>
        </div>
      </div>

      {/* Slide-over citation inspector drawer */}
      <CitationInspector
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
      />
    </div>
  );
};
