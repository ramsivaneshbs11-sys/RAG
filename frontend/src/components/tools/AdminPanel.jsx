import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Upload, FileText, Trash2, Plus, RefreshCw, CheckCircle2,
  AlertCircle, Loader2, Brain, BookOpen, ChevronDown, X, ShieldCheck,
  Database, HardDrive, Zap, BarChart3, LayoutDashboard, Activity,
  TrendingUp, Newspaper, Server, Play, Trash, RotateCcw, ArrowRight, Search
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// ── Tabs ─────────────────────────────────────────────────────────────────────
const TABS = [
  '📊 Overview Dashboard',
  '📤 PDF Ingestion Engine',
  '📁 Manage Ingested Documents',
  '📚 Syllabus & Classifications',
  '🗄️ Cache & Storage',
];

// ── Engine configs ─────────────────────────────────────────────────────────────
const ENGINES = [
  {
    id:       'v1',
    label:    'Digital PDF — Docling Engine (v1)',
    endpoint: '/api/v1/documents',
    icon:     '📄',
    desc:     'Best for text-native PDFs: NCERT textbooks, Laxmikanth, Spectrum, standard ebooks. High-speed layout extraction.',
    badge:    'FAST',
    badgeColor: 'bg-green-100 text-green-700',
  },
  {
    id:       'v2',
    label:    'Scanned / Handwritten — Gemini VLM (v2)',
    endpoint: '/api/v2/documents',
    icon:     '👁️',
    desc:     'Best for scanned books, handwritten topper notes, printed newspapers, and image-heavy PDFs. Uses Gemini 2.5 Vision.',
    badge:    'AI-POWERED',
    badgeColor: 'bg-purple-100 text-purple-700',
  },
];

// ── AdminPanel ────────────────────────────────────────────────────────────────
const AdminPanel = ({ initialTab = 0 }) => {
  const [activeTab, setActiveTab] = useState(initialTab);

  return (
    <div className="w-full h-full p-4 md:p-6 flex flex-col gap-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-upsc-maroon/10 rounded-2xl flex items-center justify-center">
          <ShieldCheck size={22} className="text-upsc-maroon" />
        </div>
        <div>
          <h2 className="text-xl font-black text-[#0f2242]">Admin Control Center</h2>
          <p className="text-xs text-gray-400 font-medium">Overview Dashboard · PDF Ingestion Engine · Document Library · Syllabus Manager</p>
        </div>
      </div>

      {/* Tab Bar — scrollable on mobile */}
      <div className="flex gap-2 p-1 bg-gray-100 rounded-2xl overflow-x-auto">
        {TABS.map((tab, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            className={`px-4 py-2.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
              activeTab === i
                ? 'bg-white text-[#0f2242] shadow-sm'
                : 'text-gray-500 hover:text-[#0f2242]'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Content — Preserved in DOM so background upload never breaks on tab switch */}
      <div className={activeTab === 0 ? "block" : "hidden"}>
        <DashboardOverview goToTab={setActiveTab} />
      </div>
      <div className={activeTab === 1 ? "block" : "hidden"}>
        <IngestionTab />
      </div>
      <div className={activeTab === 2 ? "block" : "hidden"}>
        <DocumentsManagementTab />
      </div>
      <div className={activeTab === 3 ? "block" : "hidden"}>
        <ClassificationTab />
      </div>
      <div className={activeTab === 4 ? "block" : "hidden"}>
        <CacheStorageTab />
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 0 — Admin Overview Dashboard
// ═══════════════════════════════════════════════════════════════════════════════
const DashboardOverview = ({ goToTab }) => {
  const [stats, setStats] = useState(null);
  const [docsCount, setDocsCount] = useState(null);
  const [newsStats, setNewsStats] = useState(null);
  const [cacheStats, setCacheStats] = useState(null);
  const [scraperRunning, setScraperRunning] = useState(false);
  const [scraperMsg, setScraperMsg] = useState('');
  const [activity, setActivity] = useState([]);

  const fetchStats = async () => {
    try {
      // Qdrant collections
      const r = await fetch('/api/v1/collections').catch(() => null);
      if (r && r.ok) setStats(await r.json());
    } catch (e) {}

    try {
      // Docs count from DB
      const r = await fetch('/api/v1/documents?limit=1').catch(() => null);
      if (r && r.ok) {
        const d = await r.json();
        setDocsCount(d.total ?? d.length ?? '—');
      }
    } catch (e) {}

    try {
      // News stats
      const r = await fetch('/api/v1/daily-news/stats').catch(() => null);
      if (r && r.ok) setNewsStats(await r.json());
    } catch (e) {}

    try {
      // Cache stats
      const r = await fetch('/api/v1/cache/stats').catch(() => null);
      if (r && r.ok) setCacheStats(await r.json());
    } catch (e) {}

    // Recent activity (ingestion history)
    try {
      const r = await fetch('/api/v1/documents/history?limit=5').catch(() => null);
      if (r && r.ok) {
        const d = await r.json();
        setActivity(d.documents || d || []);
      }
    } catch (e) {}
  };

  useEffect(() => { fetchStats(); }, []);

  const runNewsScraper = async () => {
    setScraperRunning(true);
    setScraperMsg('');
    try {
      const r = await fetch('/api/v1/daily-news/run-pipeline', { method: 'POST' });
      const d = await r.json();
      setScraperMsg(r.ok ? '✅ ' + (d.message || 'News pipeline completed!') : '❌ ' + (d.detail || 'Pipeline failed'));
    } catch (e) {
      setScraperMsg('❌ Could not reach pipeline endpoint.');
    }
    setScraperRunning(false);
  };

  // ── KPI Card helper ──────────────────────────────────────────────────────────
  const KpiCard = ({ icon: Icon, label, value, sub, color = 'blue', onClick }) => (
    <motion.div
      whileHover={{ scale: onClick ? 1.02 : 1, y: -2 }}
      onClick={onClick}
      className={`bg-white rounded-2xl p-5 border border-gray-100 shadow-sm flex flex-col gap-3 ${
        onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''
      }`}
    >
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
        color === 'navy'   ? 'bg-upsc-navy/10 text-upsc-navy' :
        color === 'maroon' ? 'bg-upsc-maroon/10 text-upsc-maroon' :
        color === 'green'  ? 'bg-green-100 text-green-600' :
        color === 'amber'  ? 'bg-amber-100 text-amber-600' :
        'bg-blue-100 text-blue-600'
      }`}>
        <Icon size={20} />
      </div>
      <div>
        <div className="text-2xl font-black text-[#0f2242]">{value ?? <span className="text-gray-300 text-lg">Loading…</span>}</div>
        <div className="text-xs font-bold text-gray-500 mt-0.5">{label}</div>
        {sub && <div className="text-[10px] text-gray-400 mt-1">{sub}</div>}
      </div>
    </motion.div>
  );

  // Collection health cards
  const collections = stats?.collections || [];
  const totalVectors = collections.reduce((a, c) => a + (c.vectors_count ?? 0), 0);

  return (
    <div className="flex flex-col gap-6">

      {/* KPI Row */}
      <div>
        <h3 className="text-sm font-bold text-gray-500 uppercase tracking-widest mb-3">📈 System Overview</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={FileText}   label="Ingested Documents" value={docsCount ?? '—'}  sub="PostgreSQL records" color="navy"   onClick={() => goToTab(1)} />
          <KpiCard icon={Database}   label="Total Vectors"      value={totalVectors || '—'} sub="Across all Qdrant collections" color="maroon" />
          <KpiCard icon={Newspaper}  label="News Articles"      value={newsStats?.total_articles ?? '—'} sub={newsStats?.dates_available?.[0] ? 'Latest: ' + newsStats.dates_available[0] : 'No news yet'} color="amber" />
          <KpiCard icon={Zap}        label="Cache Entries"      value={cacheStats?.total_entries ?? '—'} sub={cacheStats?.hit_rate ? `Hit rate: ${cacheStats.hit_rate}%` : 'Response cache'} color="green" onClick={() => goToTab(3)} />
        </div>
      </div>

      {/* Collection Health */}
      {collections.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-gray-500 uppercase tracking-widest mb-3">🗂️ Vector Collection Health</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {collections.map(col => (
              <div key={col.name} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex items-center justify-between">
                <div>
                  <div className="text-sm font-bold text-[#0f2242] capitalize">{col.name.replace(/_/g, ' ')}</div>
                  <div className="text-xs text-gray-500">{(col.vectors_count ?? 0).toLocaleString()} vectors</div>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                  <span className="text-[10px] font-bold text-green-600 uppercase">Healthy</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div>
        <h3 className="text-sm font-bold text-gray-500 uppercase tracking-widest mb-3">⚡ Quick Actions</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
            onClick={() => goToTab(1)}
            className="flex flex-col items-center justify-center gap-2 p-4 rounded-2xl bg-upsc-navy text-white font-bold text-xs hover:bg-upsc-navy/90 transition-all shadow-md">
            <Upload size={20} />
            <span>Ingest PDFs</span>
          </motion.button>

          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
            onClick={runNewsScraper} disabled={scraperRunning}
            className="flex flex-col items-center justify-center gap-2 p-4 rounded-2xl bg-amber-500 text-white font-bold text-xs hover:bg-amber-600 transition-all shadow-md disabled:opacity-60">
            {scraperRunning ? <Loader2 size={20} className="animate-spin" /> : <Play size={20} />}
            <span>{scraperRunning ? 'Running…' : 'Run News Scraper'}</span>
          </motion.button>

          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
            onClick={() => goToTab(3)}
            className="flex flex-col items-center justify-center gap-2 p-4 rounded-2xl bg-green-600 text-white font-bold text-xs hover:bg-green-700 transition-all shadow-md">
            <HardDrive size={20} />
            <span>Cache &amp; Storage</span>
          </motion.button>

          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
            onClick={fetchStats}
            className="flex flex-col items-center justify-center gap-2 p-4 rounded-2xl bg-gray-100 text-gray-700 font-bold text-xs hover:bg-gray-200 transition-all">
            <RotateCcw size={20} />
            <span>Refresh Stats</span>
          </motion.button>
        </div>

        {scraperMsg && (
          <motion.p initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }}
            className="text-xs font-medium text-center mt-3 text-gray-600">
            {scraperMsg}
          </motion.p>
        )}
      </div>

      {/* Recent Activity */}
      {activity.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-gray-500 uppercase tracking-widest mb-3">📜 Recent Ingestion Activity</h3>
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            {activity.slice(0, 5).map((doc, i) => (
              <div key={doc.id || i} className={`flex items-center justify-between px-4 py-3 text-xs ${
                i < activity.length - 1 ? 'border-b border-gray-50' : ''
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${
                    doc.status === 'ingested' ? 'bg-green-400' :
                    doc.status === 'failed'   ? 'bg-red-400'   : 'bg-yellow-400'
                  }`} />
                  <span className="font-medium text-gray-800 truncate max-w-[200px]">{doc.filename || doc.original_filename || 'Unknown'}</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400">
                  <span className="capitalize font-semibold">{doc.status}</span>
                  <span>{doc.chunks_created ?? ''}{doc.chunks_created ? ' chunks' : ''}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1 — PDF Ingestion Engine (Option A)
// ═══════════════════════════════════════════════════════════════════════════════
const IngestionTab = () => {
  const [engine, setEngine]   = useState('v1');
  const [classification, setClassification] = useState('Anthropology');
  const [uploadMode, setUploadMode] = useState('files'); // 'files' | 'server_folder'
  const [folderPath, setFolderPath] = useState('');
  const [files, setFiles]     = useState([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState([]);   // [{filename, status, chunks, error}]
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  const selectedEngine = ENGINES.find(e => e.id === engine);

  // ── Drag & Drop ──────────────────────────────────────────────────────────────
  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);

    // Extract files (supporting folder drop)
    const items = e.dataTransfer.items;
    if (items) {
      const extractedFiles = [];
      const queue = [];
      for (let i = 0; i < items.length; i++) {
        const entry = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
        if (entry) queue.push(entry);
        else if (items[i].kind === 'file') {
          const f = items[i].getAsFile();
          if (f && f.name.endsWith('.pdf')) extractedFiles.push(f);
        }
      }

      if (queue.length > 0) {
        let pending = queue.length;
        const traverseEntry = (entry) => {
          if (entry.isFile) {
            entry.file((file) => {
              if (file.name.endsWith('.pdf')) setFiles(prev => [...prev, file]);
            });
          } else if (entry.isDirectory) {
            const dirReader = entry.createReader();
            dirReader.readEntries((entries) => {
              entries.forEach(traverseEntry);
            });
          }
        };
        queue.forEach(traverseEntry);
      } else if (extractedFiles.length > 0) {
        setFiles(prev => [...prev, ...extractedFiles]);
      }
    } else {
      const dropped = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
      setFiles(prev => [...prev, ...dropped]);
    }
  }, []);

  const removeFile = (idx) => setFiles(prev => prev.filter((_, i) => i !== idx));

  // ── Upload Files ──────────────────────────────────────────────────────────────
  const handleUploadFiles = async () => {
    if (!files.length) return;
    setUploading(true);
    setResults([]);

    const endpoint = selectedEngine.endpoint;

    for (const file of files) {
      const formData = new FormData();
      formData.append('files', file);
      formData.append('classification', classification);

      try {
        const res = await fetch(endpoint, { method: 'POST', body: formData });
        let data = {};
        const rawText = await res.text();
        try {
          data = JSON.parse(rawText);
        } catch (parseErr) {
          data = { detail: rawText.length < 200 ? rawText : `Server error (HTTP ${res.status}). For large 100+ page PDFs, please use Server-side Folder Path.` };
        }

        if (!res.ok) {
          const errMsg = typeof data.detail === 'string' 
            ? data.detail 
            : (Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(', ') : 'Upload failed');
          setResults(prev => [...prev, { filename: file.name, status: 'error', error: errMsg }]);
        } else {
          const ingested = data.ingested || data.results || (Array.isArray(data) ? data : []);
          const totalChunks = ingested.reduce
            ? ingested.reduce((sum, r) => sum + (r.chunks_upserted ?? r.chunks ?? 0), 0)
            : 0;
          setResults(prev => [...prev, { filename: file.name, status: 'success', chunks: totalChunks }]);
        }
      } catch (err) {
        setResults(prev => [...prev, { filename: file.name, status: 'error', error: err.message }]);
      }
    }

    setUploading(false);
    setFiles([]);
  };

  // ── Server Folder Ingestion ───────────────────────────────────────────────────
  const handleIngestServerFolder = async () => {
    if (!folderPath.trim()) return;
    setUploading(true);
    setResults([]);

    try {
      const res = await fetch('/api/v1/documents/folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath.trim(), classification }),
      });
      const data = await res.json();

      if (!res.ok) {
        const errMsg = typeof data.detail === 'string' 
          ? data.detail 
          : (Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(', ') : 'Folder ingestion failed');
        setResults([{ filename: folderPath, status: 'error', error: errMsg }]);
      } else {
        const ingested = Array.isArray(data) ? data : (data.ingested || []);
        const formattedResults = ingested.map(item => ({
          filename: item.filename || item.document_id || 'PDF Document',
          status: item.status === 'error' ? 'error' : 'success',
          chunks: item.chunks_upserted ?? item.chunks ?? 0,
          error: item.error
        }));
        setResults(formattedResults);
      }
    } catch (err) {
      setResults([{ filename: folderPath, status: 'error', error: err.message }]);
    }

    setUploading(false);
  };

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {/* Engine Selector */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {ENGINES.map((eng) => (
          <button
            key={eng.id}
            type="button"
            onClick={() => setEngine(eng.id)}
            className={`text-left p-5 rounded-2xl border-2 transition-all ${
              engine === eng.id
                ? 'border-[#0f2242] bg-[#0f2242]/5 shadow-md'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-2xl">{eng.icon}</span>
              <span className={`text-[9px] font-black px-2 py-0.5 rounded-full ${eng.badgeColor}`}>{eng.badge}</span>
            </div>
            <p className="text-sm font-black text-[#0f2242] mb-1">{eng.label}</p>
            <p className="text-[11px] text-gray-500 leading-relaxed">{eng.desc}</p>
            <div className={`mt-3 w-4 h-4 rounded-full border-2 flex items-center justify-center ${engine === eng.id ? 'border-[#0f2242] bg-[#0f2242]' : 'border-gray-300'}`}>
              {engine === eng.id && <span className="w-2 h-2 bg-white rounded-full" />}
            </div>
          </button>
        ))}
      </div>

      {/* Classification Selector */}
      <div className="flex flex-col gap-1.5 bg-white p-4 rounded-2xl border border-gray-200 shadow-sm">
        <label className="text-xs font-bold text-[#0f2242] flex items-center gap-1.5">
          <BookOpen size={14} className="text-[#0f2242]" />
          Document Subject Classification <span className="text-red-500">*</span>
        </label>
        <div className="grid grid-cols-2 gap-3 mt-1">
          {['Anthropology', 'History'].map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setClassification(cat)}
              className={`py-2.5 px-4 rounded-xl text-xs font-bold transition-all border ${
                classification === cat
                  ? 'bg-[#0f2242] text-white border-[#0f2242] shadow-sm'
                  : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
              }`}
            >
              {cat === 'Anthropology' ? '🦴 Anthropology' : '📜 History'}
            </button>
          ))}
        </div>
      </div>

      {/* Upload Method Switcher */}
      <div className="flex gap-2 p-1 bg-gray-100 rounded-xl w-fit">
        <button
          type="button"
          onClick={() => setUploadMode('files')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            uploadMode === 'files' ? 'bg-white text-[#0f2242] shadow-sm' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          📄 Drag & Drop Files / Folders
        </button>
        <button
          type="button"
          onClick={() => setUploadMode('server_folder')}
          className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            uploadMode === 'server_folder' ? 'bg-white text-[#0f2242] shadow-sm' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          📁 Server-side Folder Path
        </button>
      </div>

      {/* MODE 1: File / Folder Dropzone */}
      {uploadMode === 'files' && (
        <>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-10 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all ${
              dragging ? 'border-[#0f2242] bg-[#0f2242]/5' : 'border-gray-300 bg-gray-50 hover:border-[#0f2242]/50 hover:bg-gray-100'
            }`}
          >
            <Upload size={32} className="text-gray-400" />
            <p className="text-sm font-bold text-gray-600">Drop PDF files or an entire folder here</p>
            <div className="flex gap-3 mt-1">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                className="px-3 py-1.5 rounded-lg bg-white border border-gray-300 text-xs font-bold text-[#0f2242] hover:bg-gray-50 shadow-sm"
              >
                📄 Browse Files
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }}
                className="px-3 py-1.5 rounded-lg bg-white border border-gray-300 text-xs font-bold text-[#0f2242] hover:bg-gray-50 shadow-sm"
              >
                📁 Browse Folder
              </button>
            </div>
            <p className="text-[11px] text-gray-400 mt-1">Will be ingested into <strong>{classification}</strong> collection via <strong>{selectedEngine.label}</strong></p>

            <input ref={fileInputRef} type="file" accept=".pdf" multiple className="hidden" onChange={(e) => setFiles(prev => [...prev, ...Array.from(e.target.files)])} />
            <input ref={folderInputRef} type="file" webkitdirectory="" directory="" multiple className="hidden" onChange={(e) => setFiles(prev => [...prev, ...Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'))])} />
          </div>

          {files.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
                <p className="text-xs font-black text-[#0f2242] uppercase tracking-wide">{files.length} PDF file(s) queued for {classification}</p>
                <button type="button" onClick={() => setFiles([])} className="text-[10px] text-red-400 hover:text-red-600 font-bold">Clear All</button>
              </div>
              <div className="max-h-48 overflow-y-auto">
                {files.map((file, idx) => (
                  <div key={idx} className="flex items-center gap-3 px-5 py-2.5 border-b border-gray-50 last:border-0">
                    <FileText size={16} className="text-gray-400 shrink-0" />
                    <span className="text-xs font-medium text-gray-700 flex-1 truncate">{file.name}</span>
                    <span className="text-[10px] text-gray-400">{(file.size / 1024).toFixed(0)} KB</span>
                    <button type="button" onClick={() => removeFile(idx)} className="text-gray-300 hover:text-red-400 transition-colors">
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={handleUploadFiles}
            disabled={!files.length || uploading}
            className="flex items-center justify-center gap-2 w-full py-4 rounded-2xl bg-[#0f2242] text-white font-black text-sm hover:bg-[#1a3a6b] transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-[#0f2242]/20"
          >
            {uploading ? <><Loader2 size={18} className="animate-spin" /> Ingesting {files.length} PDFs into {classification}...</> : <><Upload size={18} /> Ingest {files.length ? `${files.length} PDFs` : 'PDFs'} into {classification} Collection</>}
          </button>
        </>
      )}

      {/* MODE 2: Server-side Folder Path */}
      {uploadMode === 'server_folder' && (
        <div className="flex flex-col gap-4 bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <label className="text-xs font-bold text-[#0f2242] flex items-center gap-1.5">
            <HardDrive size={16} className="text-[#0f2242]" />
            Local Server Folder Path
          </label>
          <p className="text-xs text-gray-500 leading-relaxed">
            Enter the full absolute folder path on your computer. All <code>.pdf</code> files inside this folder (and its subfolders) will be scanned and batch-ingested into Qdrant automatically.
          </p>
          <input
            type="text"
            placeholder="e.g. C:\Users\vishn\Downloads\Anthropology_Books"
            value={folderPath}
            onChange={(e) => setFolderPath(e.target.value)}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl text-xs font-mono font-medium focus:ring-2 focus:ring-[#0f2242] focus:border-[#0f2242] outline-none"
          />

          <button
            type="button"
            onClick={handleIngestServerFolder}
            disabled={!folderPath.trim() || uploading}
            className="flex items-center justify-center gap-2 w-full py-4 rounded-2xl bg-[#0f2242] text-white font-black text-sm hover:bg-[#1a3a6b] transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-[#0f2242]/20"
          >
            {uploading ? <><Loader2 size={18} className="animate-spin" /> Batch Ingesting Server Folder into {classification}...</> : <><Database size={18} /> Batch Ingest Folder into {classification} Collection</>}
          </button>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-black text-[#0f2242] uppercase tracking-wide mb-1">Ingestion Results</p>
          <div className="max-h-64 overflow-y-auto flex flex-col gap-2">
            {results.map((r, i) => (
              <div key={i} className={`flex items-start gap-3 p-4 rounded-xl border ${r.status === 'success' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                {r.status === 'success'
                  ? <CheckCircle2 size={18} className="text-green-600 shrink-0 mt-0.5" />
                  : <AlertCircle size={18} className="text-red-500 shrink-0 mt-0.5" />}
                <div>
                  <p className="text-xs font-bold text-gray-800">{r.filename}</p>
                  {r.status === 'success'
                    ? <p className="text-[11px] text-green-700 mt-0.5">{r.chunks ? `✓ ${r.chunks} chunks indexed into Qdrant` : '✓ Successfully ingested'}</p>
                    : <p className="text-[11px] text-red-600 mt-0.5">{r.error}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2 — Document Manager & Vector Deletion
// ═══════════════════════════════════════════════════════════════════════════════
const DocumentsManagementTab = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterClass, setFilterClass] = useState('All');
  const [search, setSearch] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [toast, setToast] = useState('');

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 5000);
  };

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/documents');
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleDelete = async (doc) => {
    if (!window.confirm(`Permanently delete "${doc.original_filename}"?\n\nThis will remove all associated vector embeddings from Qdrant and delete the file from the server.`)) {
      return;
    }
    setDeletingId(doc.file_id);
    try {
      const res = await fetch(`/api/v1/documents/${doc.file_id}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok) {
        showToast(`✓ Deleted "${doc.original_filename}" (${data.qdrant_vectors_deleted ?? 0} vectors removed from Qdrant)`);
        setDocuments(prev => prev.filter(d => d.file_id !== doc.file_id));
      } else {
        showToast(`❌ Delete failed: ${data.detail || 'Server error'}`);
      }
    } catch (err) {
      showToast(`❌ Error: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = documents.filter(doc => {
    const matchesSubject = filterClass === 'All' || doc.classification === filterClass;
    const matchesSearch = !search.trim() || (doc.original_filename || '').toLowerCase().includes(search.toLowerCase());
    return matchesSubject && matchesSearch;
  });

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      {/* Toast Notification */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className={`p-3 rounded-xl text-xs font-bold flex items-center gap-2 ${
              toast.startsWith('✓') ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
            }`}
          >
            {toast.startsWith('✓') ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            {toast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header & Controls */}
      <div className="bg-white p-5 rounded-2xl border border-gray-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-black text-[#0f2242] flex items-center gap-2">
            <FileText size={18} className="text-[#0f2242]" />
            Ingested Documents Library ({documents.length})
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Manage your indexed PDFs. Deleting a document removes its vectors from Qdrant immediately.
          </p>
        </div>

        <button
          type="button"
          onClick={fetchDocuments}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 border border-gray-200 hover:bg-gray-100 rounded-xl text-xs font-bold text-gray-700 transition-all shadow-sm shrink-0"
        >
          <RotateCcw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh List
        </button>
      </div>

      {/* Search & Subject Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search documents by name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-xs font-medium focus:ring-2 focus:ring-[#0f2242] focus:border-[#0f2242] outline-none"
          />
        </div>

        <div className="flex gap-1.5 p-1 bg-gray-100 rounded-xl">
          {['All', 'Anthropology', 'History'].map(cat => (
            <button
              key={cat}
              type="button"
              onClick={() => setFilterClass(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                filterClass === cat ? 'bg-white text-[#0f2242] shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Documents List */}
      {loading ? (
        <div className="flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-gray-200 gap-3">
          <Loader2 size={24} className="animate-spin text-[#0f2242]" />
          <p className="text-xs font-bold text-gray-400">Loading ingested documents from database & Qdrant...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-gray-200 gap-2 text-center">
          <FileText size={32} className="text-gray-300" />
          <p className="text-xs font-bold text-gray-600">No documents found matching your filter</p>
          <p className="text-[11px] text-gray-400">Upload new PDFs in the "PDF Ingestion Engine" tab.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {filtered.map((doc) => (
            <div
              key={doc.file_id}
              className="flex items-center justify-between p-4 bg-white border border-gray-200 rounded-2xl hover:border-gray-300 hover:shadow-sm transition-all gap-4"
            >
              <div className="flex items-center gap-3.5 min-w-0 flex-1">
                <div className="w-10 h-10 rounded-xl bg-[#0f2242]/5 border border-[#0f2242]/10 flex items-center justify-center text-[#0f2242] shrink-0 font-bold">
                  <FileText size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-xs font-bold text-gray-900 truncate" title={doc.original_filename}>
                      {doc.original_filename}
                    </p>
                    <span className={`text-[9px] font-black px-2 py-0.5 rounded-full border ${
                      doc.classification === 'Anthropology'
                        ? 'bg-purple-50 text-purple-700 border-purple-200'
                        : 'bg-blue-50 text-blue-700 border-blue-200'
                    }`}>
                      {doc.classification}
                    </span>
                    <span className={`text-[9px] font-black px-2 py-0.5 rounded-full ${
                      doc.status === 'ingested'
                        ? 'bg-green-50 text-green-700'
                        : 'bg-red-50 text-red-700'
                    }`}>
                      {doc.status === 'ingested' ? '✓ Ingested' : '❌ Failed'}
                    </span>
                  </div>
                  <p className="text-[10px] text-gray-400 font-mono mt-1">
                    ID: {doc.file_id?.slice(0, 8)}... · Added: {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}
                  </p>
                </div>
              </div>

              {/* Delete Action Button */}
              <button
                type="button"
                onClick={() => handleDelete(doc)}
                disabled={deletingId === doc.file_id}
                className="flex items-center gap-1.5 px-3 py-2 text-red-600 hover:bg-red-50 border border-red-100 hover:border-red-200 rounded-xl text-xs font-bold transition-all disabled:opacity-50 shrink-0"
                title="Permanently delete document and Qdrant vectors"
              >
                {deletingId === doc.file_id ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    <span className="hidden sm:inline">Delete</span>
                  </>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3 — Classification Manager (Option C)
// ═══════════════════════════════════════════════════════════════════════════════
const ClassificationTab = () => {
  const [classifications, setClassifications] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [saving, setSaving]     = useState(false);
  const [form, setForm] = useState({ name: '', description: '', anchors: '' });
  const [formError, setFormError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const fetchClassifications = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/v1/classifications');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      
      const builtins = (data.builtin_classifications || ['History', 'Anthropology']).map(name => ({
        name,
        is_builtin: true,
        collection_name: `${name.toLowerCase()}_collection`,
        description: `Core UPSC subject vector store (${name}).`,
        anchors_count: 'Core Anchors'
      }));

      const dynamics = (data.dynamic_classifications || []).map(d => ({
        ...d,
        is_builtin: false
      }));

      setClassifications([...builtins, ...dynamics]);
    } catch (err) {
      setError(`Could not load classifications: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchClassifications(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    setFormError('');
    const anchors = form.anchors.split('\n').map(a => a.trim()).filter(Boolean);
    if (anchors.length < 3) {
      setFormError('Please provide at least 3 anchor sentences (one per line).');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch('/api/v1/classifications', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.name.trim(), description: form.description.trim(), anchors }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create classification');
      setSuccessMsg(`✓ Subject "${form.name}" created and Qdrant vector store provisioned!`);
      setForm({ name: '', description: '', anchors: '' });
      setShowForm(false);
      fetchClassifications();
      setTimeout(() => setSuccessMsg(''), 5000);
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`Delete classification "${name}"? This will drop its Qdrant collection and remove its syllabus anchors.`)) return;
    setDeleting(name);
    try {
      const res = await fetch(`/api/v1/classifications/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Delete failed');
      }
      setSuccessMsg(`✓ Classification "${name}" removed.`);
      fetchClassifications();
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err) {
      setError(`Delete error: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {/* Header Row */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-black text-[#0f2242]">UPSC Syllabus & Subject Classifications</p>
          <p className="text-[11px] text-gray-400">Core built-in collections and dynamically registered optional subjects.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchClassifications} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-gray-500 hover:text-[#0f2242] border border-gray-200 rounded-xl hover:bg-gray-50 transition-all">
            <RefreshCw size={13} /> Refresh
          </button>
          <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold bg-[#0f2242] text-white rounded-xl hover:bg-[#1a3a6b] transition-all">
            <Plus size={13} /> Add Subject
          </button>
        </div>
      </div>

      {/* Success Banner */}
      {successMsg && (
        <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-xl text-green-700 text-xs font-bold">
          <CheckCircle2 size={15} /> {successMsg}
        </div>
      )}

      {/* Add Form */}
      <AnimatePresence>
        {showForm && (
          <motion.form
            key="form"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            onSubmit={handleAdd}
            className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col gap-4 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-black text-[#0f2242]">Register New UPSC Subject</p>
              <button type="button" onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600">
                <X size={16} />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wide">Subject Name *</label>
                <input
                  required value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Geography, Polity, Economy"
                  className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm outline-none focus:border-[#0f2242] transition-colors"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wide">Description</label>
                <input
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="e.g. Physical & Human Geography GS-1"
                  className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm outline-none focus:border-[#0f2242] transition-colors"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wide">Anchor Sentences * (minimum 3 sentences, 1 per line)</label>
              <textarea
                required rows={5} value={form.anchors}
                onChange={e => setForm(f => ({ ...f, anchors: e.target.value }))}
                placeholder={"Physical human economic geography maps atlas topography\nIndian geography rivers mountains soil climate rainfall wind zones\nWorld geography continents oceans latitude longitude solar system"}
                className="px-4 py-3 border border-gray-200 rounded-xl text-xs outline-none focus:border-[#0f2242] transition-colors resize-none font-mono"
              />
              <p className="text-[10px] text-gray-400">The local BGE embedding classifier matches user queries against these anchor sentences to route questions automatically.</p>
            </div>

            {formError && <p className="text-xs text-red-500 font-bold flex items-center gap-1"><AlertCircle size={13}/>{formError}</p>}

            <div className="flex gap-3">
              <button type="submit" disabled={saving} className="flex items-center gap-2 px-6 py-2.5 bg-[#0f2242] text-white text-xs font-black rounded-xl hover:bg-[#1a3a6b] transition-all disabled:opacity-60 shadow-md shadow-[#0f2242]/20">
                {saving ? <><Loader2 size={14} className="animate-spin"/> Creating Collection...</> : <><Brain size={14}/> Provision Qdrant Collection</>}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="px-5 py-2.5 border border-gray-200 text-xs font-bold text-gray-500 rounded-xl hover:bg-gray-50 transition-all">
                Cancel
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Classification List */}
      {loading ? (
        <div className="flex items-center gap-3 p-6 text-gray-400">
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm font-medium">Loading syllabus classifications...</span>
        </div>
      ) : error ? (
        <div className="p-5 bg-red-50 border border-red-200 rounded-2xl text-red-600 text-xs font-bold flex items-center gap-2">
          <AlertCircle size={16}/> {error}
        </div>
      ) : classifications.length === 0 ? (
        <div className="p-8 bg-gray-50 border border-gray-200 rounded-2xl text-center">
          <BookOpen size={28} className="text-gray-300 mx-auto mb-3" />
          <p className="text-sm font-bold text-gray-400">No classifications loaded.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {classifications.map((cls, i) => (
            <div key={i} className="flex items-center gap-4 p-5 bg-white border border-gray-200 rounded-2xl hover:shadow-sm transition-all">
              <div className="w-10 h-10 rounded-xl bg-upsc-gold/10 flex items-center justify-center text-upsc-gold font-black text-sm shrink-0">
                {(cls.name || '?')[0].toUpperCase()}
              </div>
              <div className="flex-1 overflow-hidden">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-black text-[#0f2242]">{cls.name}</p>
                  <span className={`text-[8px] font-black px-2 py-0.5 rounded-full border ${
                    cls.is_builtin ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-green-50 text-green-700 border-green-200'
                  }`}>
                    {cls.is_builtin ? 'CORE SYLLABUS' : 'DYNAMIC OPTIONAL'}
                  </span>
                </div>
                {cls.description && <p className="text-[11px] text-gray-400 truncate mt-0.5">{cls.description}</p>}
                <p className="text-[10px] text-gray-400 font-mono mt-0.5">Collection: <span className="text-gray-600">{cls.collection_name}</span> {cls.anchors_count ? `· ${cls.anchors_count} anchors` : ''}</p>
              </div>
              <div className="flex items-center gap-2">
                {!cls.is_builtin ? (
                  <button
                    onClick={() => handleDelete(cls.name)}
                    disabled={deleting === cls.name}
                    className="p-2 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all disabled:opacity-50"
                    title="Delete dynamic classification"
                  >
                    {deleting === cls.name ? <Loader2 size={15} className="animate-spin"/> : <Trash2 size={15}/>}
                  </button>
                ) : (
                  <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider px-2 py-1 bg-gray-50 rounded-lg">Built-in</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};


// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3 — Cache & Storage Manager
// ═══════════════════════════════════════════════════════════════════════════════
const CacheStorageTab = () => {
  const [cacheStats, setCacheStats]     = useState(null);
  const [storageStats, setStorageStats] = useState(null);
  const [loadingCache, setLoadingCache]   = useState(true);
  const [loadingStorage, setLoadingStorage] = useState(true);
  const [clearing, setClearing]         = useState('');  // 'response' | 'articles' | 'all'
  const [toast, setToast]               = useState('');

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 4000);
  };

  const fetchCacheStats = async () => {
    setLoadingCache(true);
    try {
      const res  = await fetch('/api/v1/admin/cache/stats');
      const data = await res.json();
      setCacheStats(data);
    } catch (e) { setCacheStats({ error: e.message }); }
    finally { setLoadingCache(false); }
  };

  const fetchStorageStats = async () => {
    setLoadingStorage(true);
    try {
      const res  = await fetch('/api/v1/admin/storage/stats');
      const data = await res.json();
      setStorageStats(data);
    } catch (e) { setStorageStats({ error: e.message }); }
    finally { setLoadingStorage(false); }
  };

  useEffect(() => {
    fetchCacheStats();
    fetchStorageStats();
  }, []);

  const handleClear = async (type) => {
    const endpoint = type === 'all'      ? '/api/v1/admin/cache/all'
                   : type === 'response' ? '/api/v1/admin/cache/response'
                   :                       '/api/v1/admin/cache/articles';
    setClearing(type);
    try {
      const res  = await fetch(endpoint, { method: 'DELETE' });
      const data = await res.json();
      showToast(`✓ ${data.message}`);
      fetchCacheStats();
    } catch (e) {
      showToast(`⚠️ Error: ${e.message}`);
    } finally {
      setClearing('');
    }
  };

  const rc  = cacheStats?.response_cache  || {};
  const ac  = cacheStats?.article_cache   || {};
  const qdrant = storageStats?.qdrant     || {};
  const pg     = storageStats?.postgresql || {};
  const sqlite = storageStats?.sqlite_files || {};

  return (
    <div className="flex flex-col gap-6 max-w-3xl">

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            key="toast"
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-xl text-green-700 text-xs font-bold"
          >
            <CheckCircle2 size={15} /> {toast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Row header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <p className="text-sm font-black text-[#0f2242]">Cache & Storage Overview</p>
        <button
          onClick={() => { fetchCacheStats(); fetchStorageStats(); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-gray-500 hover:text-[#0f2242] border border-gray-200 rounded-xl hover:bg-gray-50 transition-all"
        >
          <RefreshCw size={13} /> Refresh All
        </button>
      </div>

      {/* ── SECTION 1: Response Cache ──────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-amber-500" />
            <span className="text-xs font-black text-[#0f2242]">RAG Response Cache</span>
            <span className={`text-[9px] font-black px-2 py-0.5 rounded-full ${rc.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'}`}>
              {rc.enabled ? 'ENABLED' : 'DISABLED'}
            </span>
          </div>
          <button
            onClick={() => handleClear('response')}
            disabled={!!clearing}
            className="flex items-center gap-1 px-3 py-1 text-[10px] font-black text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-all disabled:opacity-50"
          >
            {clearing === 'response' ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
            Clear
          </button>
        </div>
        {loadingCache ? (
          <div className="flex items-center gap-2 p-5 text-gray-400 text-xs"><Loader2 size={14} className="animate-spin"/> Loading...</div>
        ) : rc.error ? (
          <p className="p-4 text-xs text-red-500">{rc.error}</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-0 divide-x divide-y divide-gray-100">
            {[
              { label: 'Live Entries',    value: rc.live_entries    ?? '–' },
              { label: 'Expired',         value: rc.expired_entries ?? '–' },
              { label: 'Max Entries',     value: rc.max_entries     ?? '–' },
              { label: 'DB Size',         value: rc.db_size_mb != null ? `${rc.db_size_mb} MB` : '–' },
            ].map(({ label, value }) => (
              <div key={label} className="p-4 flex flex-col gap-1">
                <p className="text-[10px] text-gray-400 font-bold uppercase tracking-wide">{label}</p>
                <p className="text-xl font-black text-[#0f2242]">{value}</p>
              </div>
            ))}
          </div>
        )}
        <div className="px-5 py-2 bg-gray-50 border-t border-gray-100">
          <p className="text-[10px] text-gray-400">TTL: {rc.ttl_seconds ? `${(rc.ttl_seconds/86400).toFixed(0)} days` : '–'} · Path: <span className="font-mono">{rc.db_path || '–'}</span></p>
        </div>
      </div>

      {/* ── SECTION 2: Article Cache ───────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Database size={16} className="text-blue-500" />
            <span className="text-xs font-black text-[#0f2242]">Web Article Scrape Cache</span>
            <span className="text-[9px] font-black px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
              {(ac.backend || 'memory').toUpperCase()}
            </span>
          </div>
          <button
            onClick={() => handleClear('articles')}
            disabled={!!clearing}
            className="flex items-center gap-1 px-3 py-1 text-[10px] font-black text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-all disabled:opacity-50"
          >
            {clearing === 'articles' ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
            Clear
          </button>
        </div>
        {loadingCache ? (
          <div className="flex items-center gap-2 p-5 text-gray-400 text-xs"><Loader2 size={14} className="animate-spin"/> Loading...</div>
        ) : ac.error ? (
          <p className="p-4 text-xs text-red-500">{ac.error}</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-0 divide-x divide-y divide-gray-100">
            {[
              { label: 'Total Cached', value: ac.total_entries ?? (ac.redis_dbsize ?? '–') },
              { label: 'Live Entries',  value: ac.live_entries ?? '–' },
              { label: 'Max Size',      value: ac.maxsize ?? (ac.db_size_mb != null ? `${ac.db_size_mb} MB` : '–') },
            ].map(({ label, value }) => (
              <div key={label} className="p-4 flex flex-col gap-1">
                <p className="text-[10px] text-gray-400 font-bold uppercase tracking-wide">{label}</p>
                <p className="text-xl font-black text-[#0f2242]">{value}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── CLEAR ALL button ───────────────────────────────────────── */}
      <button
        onClick={() => handleClear('all')}
        disabled={!!clearing}
        className="flex items-center justify-center gap-2 w-full py-3 rounded-2xl bg-red-600 text-white font-black text-xs hover:bg-red-700 transition-all disabled:opacity-50 shadow-lg shadow-red-100"
      >
        {clearing === 'all' ? <><Loader2 size={15} className="animate-spin" /> Clearing all caches...</> : <><Trash2 size={15} /> Clear ALL Caches (Response + Articles)</>}
      </button>

      {/* ── SECTION 3: Qdrant Storage ──────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100">
          <HardDrive size={16} className="text-purple-500" />
          <span className="text-xs font-black text-[#0f2242]">Qdrant Vector Storage</span>
          <span className={`text-[9px] font-black px-2 py-0.5 rounded-full ml-auto ${qdrant.status === 'connected' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
            {qdrant.status === 'connected' ? 'CONNECTED' : 'ERROR'}
          </span>
        </div>
        {loadingStorage ? (
          <div className="flex items-center gap-2 p-5 text-gray-400 text-xs"><Loader2 size={14} className="animate-spin"/> Loading...</div>
        ) : qdrant.error ? (
          <p className="p-4 text-xs text-red-500">{qdrant.error}</p>
        ) : (
          <div className="divide-y divide-gray-50">
            {(qdrant.collections || []).map((col) => (
              <div key={col.name} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors">
                <span className="text-xs font-medium text-gray-700 font-mono">{col.name}</span>
                <span className="text-xs font-black text-[#0f2242] bg-amber-50 px-2 py-0.5 rounded-lg">
                  {col.vectors_count?.toLocaleString() || 0} vectors
                </span>
              </div>
            ))}
            {(!qdrant.collections || qdrant.collections.length === 0) && (
              <p className="p-5 text-xs text-gray-400">No collections found in Qdrant.</p>
            )}
          </div>
        )}
        <div className="px-5 py-2 bg-gray-50 border-t border-gray-100">
          <p className="text-[10px] text-gray-400">{qdrant.total_collections ?? 0} collections · PostgreSQL: {pg.status === 'connected' ? `${pg.documents_indexed} docs indexed` : (pg.error || 'error')}</p>
        </div>
      </div>

      {/* ── SECTION 4: SQLite File Sizes ───────────────────────────── */}
      {!loadingStorage && sqlite && (
        <div className="flex gap-3">
          {[
            { label: 'Response Cache DB', value: sqlite.response_cache_mb != null ? `${sqlite.response_cache_mb} MB` : 'N/A' },
            { label: 'Article Cache DB',  value: sqlite.article_cache_mb  != null ? `${sqlite.article_cache_mb} MB` : 'Memory only' },
          ].map(({ label, value }) => (
            <div key={label} className="flex-1 flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-2xl">
              <BarChart3 size={18} className="text-gray-300 shrink-0" />
              <div>
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wide">{label}</p>
                <p className="text-sm font-black text-[#0f2242]">{value}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
