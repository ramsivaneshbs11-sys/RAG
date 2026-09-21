import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Sparkles, Copy, Check, Plus, ChevronDown, Layers, FileText, Globe } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { motion, AnimatePresence } from 'framer-motion';
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
  {
    id: 'prelims',
    label: 'Prelims Mode',
    icon: Layers,
    desc: 'Direct, factual clarity with verified citations for GS-1 & Prelims.',
    badgeColor: 'bg-amber-100 text-amber-800 border-amber-200'
  },
  {
    id: 'mains',
    label: 'Mains Mode',
    icon: FileText,
    desc: 'Structured analytical framework (Intro, Key Dimensions, Way Forward).',
    badgeColor: 'bg-purple-100 text-purple-800 border-purple-200'
  },
  {
    id: 'current_affairs',
    label: 'Current Affairs',
    icon: Globe,
    desc: 'Live verified web search + daily current affairs cache.',
    badgeColor: 'bg-blue-100 text-blue-800 border-blue-200'
  }
];

const ChatInterface = () => {
  const { 
    chatHistory, addChatMessage, 
    selectedSubject, 
    chatInput, setChatInput,
    chatMode, setChatMode,
    addNote
  } = useApp();
  const [input, setInput] = useState(chatInput || '');
  const [isTyping, setIsTyping] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [statusMsg, setStatusMsg] = useState('');
  const [isModeDropdownOpen, setIsModeDropdownOpen] = useState(false);
  const scrollRef = useRef(null);
  const dropdownRef = useRef(null);
  const readerRef = useRef(null); // track active reader so we can cancel it

  useEffect(() => {
    if (chatInput) setInput(chatInput);
  }, [chatInput]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatHistory, isTyping]);

  // Close mode dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsModeDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Stage label map for pretty display
  const STAGE_LABELS = {
    cache:       '⚡ Serving from cache...',
    classifying: '🏷️ Classifying query...',
    searching:   '🔍 Searching knowledge base...',
    reranking:   '🎯 Reranking top passages...',
    generating:  '✍️ Generating answer...',
  };

  const currentModeConfig = MODES.find(m => m.id === chatMode) || MODES[0];
  const ModeIcon = currentModeConfig.icon;

  const handleSend = async () => {
    if (!input.trim()) return;

    const query = input;
    addChatMessage({ role: 'user', content: query });
    setInput('');
    setChatInput('');
    setIsTyping(true);
    setStatusMsg('🔍 Connecting...');

    try {
      const res = await fetch('/api/v1/query/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
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
        buffer = lines.pop(); // keep incomplete last chunk

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
          } catch (_) { /* skip malformed SSE lines */ }
        }
      }
    } catch (err) {
      addChatMessage({
        role:    'assistant',
        content: `⚠️ Could not reach backend. Make sure RAG-main is running on port 8000.\n\nError: ${err.message}`,
      });
    } finally {
      // Always clean up — prevents stuck loading spinner on network drops
      if (readerRef.current) {
        try { readerRef.current.cancel(); } catch (_) {}
        readerRef.current = null;
      }
      setIsTyping(false);
      setStatusMsg('');
    }
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleAddNote = (text) => {
    addNote(text);
  };

  return (
    <div className="w-full h-full p-2 md:p-4 flex flex-col flex-1">
      <div className="bg-white border border-gray-100 rounded-3xl shadow-xl overflow-hidden flex flex-col flex-1 h-[calc(100vh-3.5rem)] md:h-[calc(100vh-3.5rem)] max-h-[calc(100vh-4.5rem-env(safe-area-inset-bottom))]">
        {/* Chat Header */}
        <div className="flex items-center justify-between p-4 md:p-5 border-b border-gray-100 bg-white relative z-20">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center font-bold shadow-sm">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="text-lg font-black text-[#0f2242]">Ask UPSC AI</h2>
              <p className="text-[10px] text-green-600 font-bold uppercase tracking-wider flex items-center gap-1 mt-0.5">
                <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" /> AI Mentor Online
              </p>
            </div>
          </div>

          {/* Mode Selector Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setIsModeDropdownOpen(!isModeDropdownOpen)}
              className="flex items-center gap-2 px-3 py-2 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-2xl transition-all text-xs font-bold text-[#0f2242]"
            >
              <ModeIcon size={15} className="text-amber-600" />
              <span>{currentModeConfig.label}</span>
              <ChevronDown size={14} className={`text-gray-400 transition-transform ${isModeDropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            <AnimatePresence>
              {isModeDropdownOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 8, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 mt-2 w-72 bg-white border border-gray-200 rounded-2xl shadow-xl p-2 flex flex-col gap-1 z-30"
                >
                  <p className="text-[10px] font-black text-gray-400 uppercase tracking-wider px-3 py-1">Select Response Mode</p>
                  {MODES.map((m) => {
                    const Icon = m.icon;
                    const isSelected = (chatMode || 'prelims') === m.id;
                    return (
                      <button
                        key={m.id}
                        onClick={() => {
                          setChatMode(m.id);
                          setIsModeDropdownOpen(false);
                        }}
                        className={`text-left p-2.5 rounded-xl transition-all flex items-start gap-2.5 ${
                          isSelected ? 'bg-amber-50/80 border border-amber-200' : 'hover:bg-gray-50'
                        }`}
                      >
                        <div className={`p-1.5 rounded-lg shrink-0 mt-0.5 ${isSelected ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-500'}`}>
                          <Icon size={14} />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-[#0f2242]">{m.label}</span>
                            {isSelected && <Check size={12} className="text-amber-600" />}
                          </div>
                          <p className="text-[10px] text-gray-400 leading-tight mt-0.5">{m.desc}</p>
                        </div>
                      </button>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Messages Body */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 bg-gray-50/30" style={{ willChange: 'transform', WebkitOverflowScrolling: 'touch' }}>
          {chatHistory.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto py-12">
              <div className="w-16 h-16 bg-amber-50 text-amber-600 rounded-3xl flex items-center justify-center mb-4">
                <Bot size={36} />
              </div>
              <h3 className="text-xl font-black text-[#0f2242] mb-2">How can I help you today?</h3>
              <p className="text-gray-500 text-xs leading-relaxed">
                I can help you with Prelims MCQs, Mains Answer Writing, or understanding complex Polity and History topics.
              </p>
            </div>
          )}

          {chatHistory.map((msg, i) => (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              key={i}
              className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div className={`w-9 h-9 rounded-2xl flex items-center justify-center shrink-0 text-xs font-bold ${
                msg.role === 'user' ? 'bg-[#0f2242] text-white' : 'bg-amber-50 text-amber-600 border border-amber-200'
              }`}>
                {msg.role === 'user' ? <User size={18} /> : <Sparkles size={18} />}
              </div>
              <div className={`max-w-[80%] p-4 md:p-5 rounded-2xl text-xs md:text-sm leading-relaxed relative group ${
                msg.role === 'user' ? 'bg-[#0f2242] text-white shadow-md' : 'bg-white border border-gray-100 text-[#0f2242] font-medium shadow-sm'
              }`}>
                {msg.role === 'user' ? (
                  msg.content
                ) : (
                  <div className="prose prose-sm max-w-none prose-headings:text-[#0f2242] prose-headings:font-black prose-strong:text-[#0f2242] prose-li:marker:text-amber-500 prose-hr:border-gray-200">
                    <ReactMarkdown
                      components={{
                        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                        ul: ({ children }) => <ul className="list-disc pl-4 space-y-1 mb-2">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal pl-4 space-y-1 mb-2">{children}</ol>,
                        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                        strong: ({ children }) => <strong className="font-bold text-[#0f2242]">{children}</strong>,
                        h3: ({ children }) => <h3 className="font-black text-sm text-[#0f2242] mt-3 mb-1">{children}</h3>,
                        h4: ({ children }) => <h4 className="font-bold text-xs text-[#0f2242] mt-2 mb-1">{children}</h4>,
                        hr: () => <hr className="my-3 border-gray-200" />,
                      }}
                    >
                      {cleanAnswer(msg.content)}
                    </ReactMarkdown>
                  </div>
                )}
                
                {msg.role === 'assistant' && (
                  <div className="absolute -bottom-8 right-0 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button 
                      onClick={() => handleCopy(msg.content, i)}
                      className="p-1 bg-white border border-gray-200 rounded-lg text-gray-500 hover:text-[#0f2242] transition-colors flex items-center gap-1 text-[10px] font-bold shadow-sm"
                    >
                      {copiedId === i ? <Check size={12} /> : <Copy size={12} />}
                      {copiedId === i ? 'COPIED' : 'COPY'}
                    </button>
                    <button 
                      onClick={() => handleAddNote(msg.content)}
                      className="p-1 bg-white border border-gray-200 rounded-lg text-gray-500 hover:text-amber-600 transition-colors flex items-center gap-1 text-[10px] font-bold shadow-sm"
                    >
                      <Plus size={12} /> ADD NOTE
                    </button>
                  </div>
                )}
              </div>
            </motion.div>
          ))}

          {isTyping && (
            <div className="flex gap-3">
              <div className="w-9 h-9 bg-amber-50 text-amber-600 border border-amber-200 rounded-2xl flex items-center justify-center shrink-0">
                <Sparkles size={18} className="animate-pulse" />
              </div>
              <div className="bg-white border border-gray-100 p-3 rounded-2xl flex items-center gap-2 shadow-sm">
                <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-bounce" />
                {statusMsg && (
                  <span className="text-[10px] font-bold text-amber-700 ml-2 uppercase tracking-wide">{statusMsg}</span>
                )}
              </div>
            </div>
          )}

        </div>

        {/* Input Bar */}
        <div className="p-4 md:p-6 bg-white border-t border-gray-100">
          <div className="relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !isTyping && handleSend()}
              placeholder={isTyping ? 'Generating answer...' : 'Ask your UPSC doubt...'}
              disabled={isTyping}
              className="w-full pl-5 pr-32 py-4 bg-gray-50 border border-gray-200 rounded-2xl shadow-sm focus:border-[#0f2242] transition-all text-[#0f2242] text-sm outline-none placeholder:text-gray-400 font-medium disabled:opacity-60 disabled:cursor-not-allowed"
            />
            <button 
              onClick={handleSend}
              disabled={!input.trim() || isTyping}
              className="absolute right-2 top-2 bottom-2 px-5 bg-[#0f2242] hover:bg-[#1a3a6b] text-white rounded-xl font-bold text-xs flex items-center gap-2 transition-all disabled:opacity-50"
            >
              Ask Mentor <Send size={15} />
            </button>
          </div>
          <p className="text-center text-[10px] text-gray-400 mt-3 uppercase tracking-widest font-bold">
            Empowered by UPSC AI Advanced Models
          </p>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
