import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { Sparkles, Send, Paperclip, ChevronDown, Bot, GraduationCap, Globe2, BookOpen, ChevronRight, User, Layers, FileText, Globe, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Logo from '../Logo';
import { dummyQuestions } from '../../data/dummyData';
import ReactMarkdown from 'react-markdown';

// Strip all citation tags (chk_001), [chk_001], (chk_001, chk_002) from LLM responses safely
const cleanAnswer = (text) => {
  if (!text) return '';
  if (typeof text !== 'string') {
    try {
      text = JSON.stringify(text);
    } catch {
      text = String(text);
    }
  }
  return text
    .replace(/\((?:chk_\w+[\s,]*)+\)/gi, '') // removes (chk_0030, chk_0027)
    .replace(/\[(?:chk_\w+[\s,]*)+\]/gi, '') // removes [chk_0001]
    .replace(/chk_\w+/gi, '')                 // removes bare chk_xxx
    .replace(/\(\s*,?\s*\)/g, '')            // removes leftover empty parens
    .replace(/\s+([.,;:!?])/g, '$1')         // fix 'press .' -> 'press.'
    .replace(/  +/g, ' ')
    .trim();
};

const MODES = [
  { id: 'prelims', label: 'Prelims', icon: Layers, desc: 'Factual clarity & MCQs' },
  { id: 'mains', label: 'Mains', icon: FileText, desc: 'Structured analysis' },
  { id: 'current_affairs', label: 'Current Affairs', icon: Globe, desc: 'Live web & CA digest' },
];

const MobileChat = () => {
  const { 
    chatHistory, addChatMessage, 
    selectedSubject, setSelectedSubject, 
    chatInput, setChatInput,
    chatMode, setChatMode,
    addNote
  } = useApp();
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isModeOpen, setIsModeOpen] = useState(false);
  const scrollRef = useRef(null);
  const modeDropdownRef = useRef(null);
  const readerRef = useRef(null);

  const STAGE_LABELS = {
    cache:       '⚡ Serving from cache...',
    classifying: '🏷️ Classifying query...',
    searching:   '🔍 Searching knowledge base...',
    reranking:   '🎯 Reranking top passages...',
    generating:  '✍️ Generating answer...',
  };

  const currentMode = MODES.find(m => m.id === chatMode) || MODES[0];
  const ModeIcon = currentMode.icon;

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [chatHistory, isTyping]);

  // Close mode dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (modeDropdownRef.current && !modeDropdownRef.current.contains(e.target)) {
        setIsModeOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSend = async (text = input) => {
    const messageText = typeof text === 'string' ? text : input;
    if (!messageText.trim()) return;

    addChatMessage({ role: 'user', content: messageText });
    setInput('');
    setIsTyping(true);
    setStatusMsg('🔍 Connecting...');

    try {
      const res = await fetch('/api/v1/query/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query:      messageText,
          mode:       chatMode || 'prelims',
          session_id: 'session_default',
        }),
      });

      if (!res.ok) throw new Error(`Backend error: ${res.status}`);

      const reader  = res.body.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === 'progress') {
              setStatusMsg(STAGE_LABELS[event.stage] || event.message);
            } else if (event.type === 'result') {
              const data = event.payload;
              let citationBlock = '';
              if (data.chunks && data.chunks.length > 0) {
                const sources = data.chunks
                  .filter(c => c.metadata?.source)
                  .map(c => `• ${c.metadata.source}`)
                  .filter((v, i, a) => a.indexOf(v) === i)
                  .slice(0, 5)
                  .join('\n');
                if (sources) citationBlock = `\n\nSources:\n${sources}`;
              }
              addChatMessage({
                role:    'assistant',
                content: (data.answer || 'No answer returned.') + citationBlock,
              });
            } else if (event.type === 'done') {
              setIsTyping(false);
              setStatusMsg('');
            } else if (event.type === 'error') {
              throw new Error(event.message);
            }
          } catch (_) { /* skip malformed lines */ }
        }
      }
    } catch (err) {
      addChatMessage({
        role:    'assistant',
        content: `⚠️ Could not reach backend. Make sure RAG-main is running on port 8000.\n\nError: ${err.message}`,
      });
    } finally {
      if (readerRef.current) {
        try { readerRef.current.cancel(); } catch (_) {}
        readerRef.current = null;
      }
      setIsTyping(false);
      setStatusMsg('');
    }
  };

  const stats = [
    { label: 'Exam', value: 'UPSC 2026', icon: GraduationCap, color: 'text-blue-500', bg: 'bg-blue-50' },
    { label: 'Lang', value: 'English', icon: Globe2, color: 'text-green-500', bg: 'bg-green-50' },
    { label: 'Progress', value: '42%', icon: BookOpen, color: 'text-purple-500', bg: 'bg-purple-50' },
  ];

  return (
    <div className="flex flex-col h-screen bg-[#F8FAFC]">
      {/* Mobile Header */}
      <header className="bg-white border-b border-slate-100 px-4 py-3 flex items-center justify-between sticky top-0 z-50 shadow-sm">
        <div className="flex items-center gap-2.5">
          <Logo showText={false} className="h-8 w-auto" />
          <div className="flex flex-col">
            <h1 className="text-base font-black text-upsc-navy leading-none">UPSC AI</h1>
            <div className="flex items-center gap-1 mt-1">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[9px] font-bold text-green-600 uppercase tracking-wider">AI Online</span>
            </div>
          </div>
        </div>

        {/* Mode Selector */}
        <div className="relative" ref={modeDropdownRef}>
          <button
            onClick={() => setIsModeOpen(!isModeOpen)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-[11px] font-bold text-upsc-navy"
          >
            <ModeIcon size={13} className="text-amber-600" />
            <span>{currentMode.label}</span>
            <ChevronDown size={12} className={`text-slate-400 transition-transform ${isModeOpen ? 'rotate-180' : ''}`} />
          </button>

          <AnimatePresence>
            {isModeOpen && (
              <motion.div
                initial={{ opacity: 0, y: 6, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 6, scale: 0.95 }}
                className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-2xl shadow-xl p-2 flex flex-col gap-1 z-50"
              >
                {MODES.map((m) => {
                  const Icon = m.icon;
                  const isSelected = (chatMode || 'prelims') === m.id;
                  return (
                    <button
                      key={m.id}
                      onClick={() => {
                        setChatMode(m.id);
                        setIsModeOpen(false);
                      }}
                      className={`text-left p-2 rounded-xl transition-all flex items-center gap-2 ${
                        isSelected ? 'bg-amber-50 border border-amber-200' : 'hover:bg-slate-50'
                      }`}
                    >
                      <Icon size={14} className={isSelected ? 'text-amber-600' : 'text-slate-400'} />
                      <div className="flex-1">
                        <p className="text-xs font-bold text-upsc-navy">{m.label}</p>
                        <p className="text-[9px] text-slate-400">{m.desc}</p>
                      </div>
                      {isSelected && <Check size={12} className="text-amber-600" />}
                    </button>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </header>

      {/* Main Content Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto pb-40 scroll-smooth" style={{ willChange: 'transform', WebkitOverflowScrolling: 'touch' }}>
        {chatHistory.length === 0 ? (
          <div className="px-6 py-8">
            <div className="mb-10">
              <h2 className="text-3xl font-black text-upsc-navy mb-2">Hello Aspirant!</h2>
              <p className="text-slate-500 text-sm leading-relaxed">Your AI-powered mentor is ready. What would you like to learn today?</p>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3 mb-10">
              {stats.map((stat, i) => (
                <div key={i} className={`${stat.bg} rounded-2xl p-3 flex flex-col items-center text-center`}>
                  <stat.icon size={18} className={stat.color} />
                  <p className="text-[9px] font-bold text-slate-400 uppercase mt-2 mb-0.5">{stat.label}</p>
                  <p className="text-[11px] font-black text-upsc-navy">{stat.value}</p>
                </div>
              ))}
            </div>

            {/* Quick Questions */}
            <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4">Suggested Topics</h3>
            <div className="grid gap-3">
              {dummyQuestions.slice(0, 4).map((q) => (
                <button
                  key={q.id}
                  onClick={() => handleSend(q.title)}
                  className="bg-white border border-slate-100 p-4 rounded-[20px] text-left flex items-center justify-between group active:scale-[0.98] transition-all shadow-sm"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-1.5 h-10 rounded-full ${
                      q.color === 'orange' ? 'bg-upsc-gold' : q.color === 'blue' ? 'bg-blue-500' : 'bg-green-500'
                    }`} />
                    <div>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{q.category}</p>
                      <p className="text-sm font-bold text-upsc-navy leading-tight">{q.title}</p>
                    </div>
                  </div>
                  <ChevronRight size={18} className="text-slate-300" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="p-6 space-y-6">
            {chatHistory.map((msg, i) => (
              <motion.div 
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${
                  msg.role === 'user' ? 'bg-upsc-navy text-white' : 'bg-white border border-slate-100 text-upsc-gold shadow-sm'
                }`}>
                  {msg.role === 'user' ? <User size={16} /> : <Sparkles size={16} />}
                </div>
                <div className={`max-w-[85%] p-4 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'user' ? 'bg-upsc-navy text-white shadow-lg shadow-upsc-navy/10' : 'bg-white border border-slate-100 text-slate-700 font-medium shadow-sm'
                }`}>
                  {msg.role === 'user' ? (
                    msg.content
                  ) : (
                    <div className="prose prose-sm max-w-none prose-headings:text-upsc-navy prose-headings:font-black prose-strong:text-upsc-navy prose-li:marker:text-amber-500">
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => <p className="mb-2 last:mb-0 text-slate-700">{children}</p>,
                          ul: ({ children }) => <ul className="list-disc pl-4 space-y-1 mb-2">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal pl-4 space-y-1 mb-2">{children}</ol>,
                          li: ({ children }) => <li className="text-slate-700 leading-relaxed">{children}</li>,
                          strong: ({ children }) => <strong className="font-bold text-upsc-navy">{children}</strong>,
                          h3: ({ children }) => <h3 className="font-black text-sm text-upsc-navy mt-3 mb-1">{children}</h3>,
                          h4: ({ children }) => <h4 className="font-bold text-xs text-upsc-navy mt-2 mb-1">{children}</h4>,
                          hr: () => <hr className="my-3 border-slate-200" />,
                        }}
                      >
                        {cleanAnswer(msg.content)}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
            {isTyping && (
              <div className="flex gap-3">
                <div className="w-8 h-8 bg-white border border-slate-100 text-upsc-gold rounded-xl flex items-center justify-center shrink-0">
                  <Sparkles size={16} className="animate-pulse" />
                </div>
                <div className="bg-white border border-slate-100 p-4 rounded-2xl flex gap-1 shadow-sm">
                  <span className="w-1.5 h-1.5 bg-upsc-gold/40 rounded-full animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 bg-upsc-gold/40 rounded-full animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 bg-upsc-gold/40 rounded-full animate-bounce" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="fixed bottom-[88px] left-0 right-0 px-6 pb-4 bg-transparent z-50">
        <div className="bg-white/80 backdrop-blur-xl border border-slate-100 p-2 rounded-[28px] shadow-2xl flex items-center gap-2">
          <button className="p-3 text-slate-400 hover:text-upsc-navy transition-colors">
            <Paperclip size={20} />
          </button>
          <input 
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && !isTyping && handleSend()}
            placeholder={isTyping ? 'Generating answer...' : 'Ask your doubt...'}
            disabled={isTyping}
            className="flex-1 bg-transparent border-none focus:ring-0 text-sm font-bold text-upsc-navy placeholder:text-slate-400 disabled:opacity-60"
          />
          <button 
            onClick={() => handleSend()}
            disabled={!input.trim() || isTyping}
            className="bg-gradient-to-r from-upsc-navy to-upsc-maroon text-white p-3 rounded-[20px] shadow-lg shadow-upsc-navy/20 active:scale-90 transition-all disabled:opacity-50 disabled:scale-100"
          >
            <Send size={20} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default MobileChat;
