import React, { useEffect, useState, useRef } from 'react';
import { api } from '../lib/api';
import { DocumentItem } from '../types';
import { useAuth } from '../context/AuthContext';
import { StatusBadge } from '../components/StatusBadge';
import {
  UploadCloud,
  FileText,
  Trash2,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Search,
  Filter,
} from 'lucide-react';

export const DocumentsPage: React.FC = () => {
  const { hasRole } = useAuth();
  const canManage = hasRole(['SUPER_ADMIN', 'ORG_ADMIN', 'KNOWLEDGE_MANAGER']);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDepartment, setSelectedDepartment] = useState<string>('');

  // Upload state
  const [dragActive, setDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const res = await api.getDocuments(1, 100, selectedDepartment || undefined);
      setDocuments(res.items);
    } catch (err: any) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    // Polling for processing status update every 5 seconds if any doc is processing
    const interval = setInterval(() => {
      const hasActive = documents.some((d) =>
        ['UPLOADED', 'PARSING', 'CHUNKING', 'EMBEDDING'].includes(d.status)
      );
      if (hasActive) {
        fetchDocuments();
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [selectedDepartment]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileUpload = async (file: File) => {
    setUploadError(null);
    setUploadSuccess(null);
    setUploadProgress(0);

    // Validate extension
    const allowed = ['.pdf', '.docx', '.txt'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      setUploadError(`Unsupported file format. Please upload ${allowed.join(', ')}`);
      setUploadProgress(null);
      return;
    }

    try {
      await api.uploadDocument(file, selectedDepartment || undefined, (pct) => {
        setUploadProgress(pct);
      });
      setUploadSuccess(`"${file.name}" uploaded successfully and queued for ingestion!`);
      setUploadProgress(null);
      fetchDocuments();
    } catch (err: any) {
      setUploadError(err.message || 'Failed to upload document');
      setUploadProgress(null);
    }
  };

  const handleDelete = async (docId: string, title: string) => {
    if (!window.confirm(`Are you sure you want to delete "${title}"?`)) return;
    try {
      await api.deleteDocument(docId);
      setDocuments(documents.filter((d) => d.id !== docId));
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const filteredDocs = documents.filter((doc) =>
    doc.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Document Library</h1>
          <p className="text-sm text-slate-400 mt-1">
            Enterprise knowledge repository for layout-aware chunking and pgvector search.
          </p>
        </div>

        <button
          onClick={fetchDocuments}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl border border-slate-700/60 transition-colors self-start sm:self-auto"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Upload Box (Only for Knowledge Managers & Admins) */}
      {canManage && (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-sm space-y-4">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-indigo-400" />
            Upload New Document
          </h2>

          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
              dragActive
                ? 'border-indigo-500 bg-indigo-500/10'
                : 'border-slate-800 hover:border-slate-700 bg-slate-950/40'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileUpload(e.target.files[0]);
                }
              }}
            />
            <div className="flex flex-col items-center gap-2">
              <div className="w-12 h-12 rounded-full bg-indigo-600/10 text-indigo-400 flex items-center justify-center">
                <UploadCloud className="w-6 h-6" />
              </div>
              <p className="text-sm font-medium text-slate-200">
                Drag and drop your file here, or <span className="text-indigo-400">browse</span>
              </p>
              <p className="text-xs text-slate-500">
                Supported formats: PDF, DOCX, TXT (up to 50MB)
              </p>
            </div>
          </div>

          {/* Progress bar */}
          {uploadProgress !== null && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Uploading...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-500 transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Alerts */}
          {uploadError && (
            <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {uploadError}
            </div>
          )}
          {uploadSuccess && (
            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {uploadSuccess}
            </div>
          )}
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3 pointer-events-none" />
            <input
              type="text"
              placeholder="Search documents by title..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl py-2 pl-9 pr-4 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder="Filter Dept ID..."
              value={selectedDepartment}
              onChange={(e) => setSelectedDepartment(e.target.value)}
              className="w-36 bg-slate-900 border border-slate-800 rounded-xl py-2 px-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        <div className="text-xs text-slate-500">
          Showing <span className="font-semibold text-slate-300">{filteredDocs.length}</span> documents
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
              <tr>
                <th className="px-6 py-4">Document Title</th>
                <th className="px-6 py-4">Format</th>
                <th className="px-6 py-4">Size</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Chunks</th>
                <th className="px-6 py-4">Uploaded</th>
                {canManage && <th className="px-6 py-4 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredDocs.length === 0 ? (
                <tr>
                  <td colSpan={canManage ? 7 : 6} className="px-6 py-12 text-center text-slate-500">
                    No documents found in this organization.
                  </td>
                </tr>
              ) : (
                filteredDocs.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-6 py-4 font-medium text-slate-100 flex items-center gap-3">
                      <FileText className="w-4 h-4 text-indigo-400 shrink-0" />
                      <span className="truncate max-w-xs">{doc.title}</span>
                    </td>
                    <td className="px-6 py-4 uppercase font-mono text-[11px] text-slate-400">
                      {doc.file_type}
                    </td>
                    <td className="px-6 py-4 font-mono text-slate-400">
                      {formatFileSize(doc.file_size)}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-6 py-4 font-mono text-slate-300">
                      {doc.total_chunks ?? 0}
                    </td>
                    <td className="px-6 py-4 text-slate-400">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    {canManage && (
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleDelete(doc.id, doc.title)}
                          className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition-colors"
                          title="Delete Document"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
