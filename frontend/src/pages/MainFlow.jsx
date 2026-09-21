import React, { useState, useEffect, useRef } from 'react';
import { Send, Lock, CheckCircle2, ChevronRight, MessageSquare, BookOpen, Newspaper, Star, Loader2, ArrowRight, ChevronLeft, PanelLeftClose, PanelLeftOpen, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import Logo from '../components/Logo';
import { useApp } from '../context/AppContext';
import './MainFlow.css';

const MainFlow = () => {
  const [step, setStep] = useState(1);
  
  // Step 1: Identity Gateway State
  const [identityData, setIdentityData] = useState({
    firstName: 'Arjun',
    lastName: 'Kumar',
    email: 'arjun.k@examprep.in',
    phone: '+91 9876543210'
  });

  // Step 2: OTP State
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [timeLeft, setTimeLeft] = useState(15);
  const otpRefs = useRef([]);

  // Step 3: Specialization State
  const [specialization, setSpecialization] = useState('History');

  // Step 4 & 5: Chat State
  const [queriesUsed, setQueriesUsed] = useState(0);
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef(null);

  // Step 7: Dashboard Mode
  const [dashboardMode, setDashboardMode] = useState('prelims');
  const [showTooltip, setShowTooltip] = useState(true);
  const [activeView, setActiveView] = useState('chat'); // chat, notes, news
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  
  const { notes, deleteNote } = useApp();

  // Focus management
  const firstNameRef = useRef(null);
  const chatInputRef = useRef(null);

  // Per-page document title
  useEffect(() => {
    document.title = 'UPSC Preparation Workflow | UPSC AI';
  }, []);

  useEffect(() => {
    if (step === 1 && firstNameRef.current) {
        firstNameRef.current.focus();
    }
    if (step === 2) {
      if (otpRefs.current[0]) otpRefs.current[0].focus();
      const timer = setInterval(() => {
        setTimeLeft(prev => prev > 0 ? prev - 1 : 0);
      }, 1000);
      return () => clearInterval(timer);
    }
    if (step === 4 && chatInputRef.current) {
      chatInputRef.current.focus();
    }
    if (step === 7) {
      setTimeout(() => setShowTooltip(false), 5000);
    }
  }, [step]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  /* --- Handlers --- */
  const handleIdentitySubmit = (e) => {
    e.preventDefault();
    if (identityData.phone.length === 10) {
      setStep(2);
    }
  };

  const handleOtpChange = (index, value) => {
    if (isNaN(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);

    // Auto next box
    if (value !== '' && index < 5) {
      otpRefs.current[index + 1].focus();
    }
    // Auto submit
    if (index === 5 && value !== '' && newOtp.every(v => v !== '')) {
      setTimeout(() => setStep(3), 400);
    }
  };

  const handleOtpKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      otpRefs.current[index - 1].focus();
    }
  };

  const handleChatSubmit = async (e) => {
    e?.preventDefault();
    if (!chatInput.trim() || isTyping) return;

    if (queriesUsed >= 3) {
      setStep(5); // Trigger Overlay
      return;
    }

    const newQuery = chatInput;
    setMessages(prev => [...prev, { role: 'user', content: newQuery }]);
    setChatInput('');
    setQueriesUsed(prev => prev + 1);
    setIsTyping(true);

    try {
      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query:      newQuery,
          mode:       dashboardMode || 'prelims',
          session_id: 'session_default',
        }),
      });

      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();

      // Build citation links if available
      let citationBlock = '';
      if (data.chunks && data.chunks.length > 0) {
        const sources = data.chunks
          .filter(c => c.metadata?.source)
          .map(c => `- ${c.metadata.source}`)
          .filter((v, i, a) => a.indexOf(v) === i) // dedupe
          .slice(0, 5)
          .join('\n');
        if (sources) citationBlock = `\n\n**Sources:**\n${sources}`;
      }

      setMessages(prev => [...prev, {
        role:    'ai',
        content: (data.answer || 'No answer returned.') + citationBlock,
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role:    'ai',
        content: `⚠️ Could not reach the RAG backend. Make sure it is running at **http://localhost:8000**.\n\nError: ${err.message}`,
      }]);
    } finally {
      setIsTyping(false);
    }
  };


  const suggestQuestion = (q) => {
    setChatInput(q);
    // setTimeout(() => handleChatSubmit(), 100);
  };

  /* --- Renders --- */
  const renderProgress = (text) => (
    <div className="progress-indicator">
      <span>{text}</span>
      <div className="progress-bar"><div className="progress-fill" style={{width: `${(step/7)*100}%`}}></div></div>
    </div>
  );

  return (
    <div className="app-container">
      {/* STEP 1: IDENTITY GATEWAY */}
      {step === 1 && (
        <div className="step-container identity-gateway">
          {renderProgress('Step 1 of 7')}
          <div className="card text-center fade-in">
            <div className="mb-8 flex justify-center"><Logo showText={true} /></div>
            <p className="subtext">Empowering Aspirants with AI-Driven Excellence</p>
            
            <form onSubmit={handleIdentitySubmit}>
              <input ref={firstNameRef} type="text" placeholder="First Name" required value={identityData.firstName} onChange={e => setIdentityData({...identityData, firstName: e.target.value})} />
              <input type="text" placeholder="Last Name" required value={identityData.lastName} onChange={e => setIdentityData({...identityData, lastName: e.target.value})} />
              <input type="email" placeholder="Email Address" required value={identityData.email} onChange={e => setIdentityData({...identityData, email: e.target.value})} />
              <input 
                type="tel" 
                placeholder="Phone Number" 
                required 
                value={identityData.phone} 
                onChange={e => {
                  const val = e.target.value.replace(/\D/g, '');
                  if (val.length <= 10) setIdentityData({...identityData, phone: val});
                }} 
                maxLength={10}
              />
              <button 
                type="submit" 
                className="btn-primary mt-4" 
                disabled={identityData.phone.length !== 10}
              >
                Continue <ArrowRight size={18} />
              </button>
            </form>
          </div>
        </div>
      )}

      {/* STEP 2: OTP SECURITY */}
      {step === 2 && (
        <div className="step-container otp-security">
          {renderProgress('Step 2 of 7')}
          <div className="card text-center fade-in">
            <h2>Verify Your Number</h2>
            <p className="subtext">We've sent a 6-digit code to {identityData.phone}</p>
            
            <div className="otp-container">
              {otp.map((d, i) => (
                <input
                  key={i}
                  ref={el => otpRefs.current[i] = el}
                  type="text"
                  maxLength="1"
                  value={d}
                  onChange={e => handleOtpChange(i, e.target.value)}
                  onKeyDown={e => handleOtpKeyDown(i, e)}
                  className="otp-box"
                />
              ))}
            </div>
            
            <div className="resend-text">
              {timeLeft > 0 ? `Resend OTP in ${timeLeft}s` : <button className="btn-text" onClick={() => setTimeLeft(15)}>Resend OTP</button>}
            </div>
          </div>
        </div>
      )}

      {/* STEP 3: SPECIALIZATION SELECTION */}
      {step === 3 && (
        <div className="step-container spec-selection">
          {renderProgress('Step 3 of 7')}
          <div className="card text-center fade-in max-w-md">
            <h2>Choose Your Specialization</h2>
            <p className="subtext">Select an optional subject to personalize your learning</p>

            <div className="spec-options">
              <div className={`spec-card ${specialization === 'History' ? 'selected' : ''}`} onClick={() => setSpecialization('History')}>
                <div className="spec-info">
                  <h3>History</h3>
                  <p>Static + high scoring</p>
                </div>
                {specialization === 'History' && <CheckCircle2 className="check-icon" />}
              </div>
              <div className={`spec-card ${specialization === 'Anthropology' ? 'selected' : ''}`} onClick={() => setSpecialization('Anthropology')}>
                <div className="spec-info">
                  <h3>Anthropology</h3>
                  <p>Optional-focused</p>
                </div>
                {specialization === 'Anthropology' && <CheckCircle2 className="check-icon" />}
              </div>
              
              <div className="spec-card locked" style={{ cursor: 'not-allowed' }}>
                <div className="spec-info">
                  <h3>Geography</h3>
                  <p>Coming Soon</p>
                </div>
                <Lock size={18} className="lock-icon" />
              </div>
            </div>

            <button className="btn-primary mt-6 w-full" onClick={() => setStep(4)}>Continue <ArrowRight size={18} /></button>
          </div>
        </div>
      )}

      {/* STEP 4: CHAT PAGE & STEP 5: OVERLAY */}
      {(step === 4 || step === 5) && (
        <div className="step-container chat-layout fade-in">
          <header className="chat-header">
            <div className="brand text-upsc-navy"><Logo showText={false} className="h-8 w-auto" /> <span className="ml-2 font-bold">Selva's AI</span></div>
            <div className="queries-badge">{3 - queriesUsed} Free Questions Remaining</div>
          </header>

          <main className="chat-body">
            {messages.length === 0 && (
               <div className="chat-empty">
                 <div className="mb-6"><Logo showText={false} className="h-16 w-auto" /></div>
                 <h2>What do you want to master today?</h2>
                 <div className="suggestions">
                   <button className="chip" onClick={() => suggestQuestion("What is Indus Valley Civilization?")}>"What is Indus Valley Civilization?"</button>
                   <button className="chip" onClick={() => suggestQuestion("Explain Tribal Society in India")}>"Explain Tribal Society in India"</button>
                 </div>
               </div>
            )}
            
            <div className="messages-list">
              {messages.map((msg, i) => (
                <div key={i} className={`msg-wrapper ${msg.role}`}>
                  <div className="msg-bubble">
                    {msg.role === 'ai' ? (
                      <div className="formatted-content prose prose-sm max-w-none">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            strong: ({ children }) => <strong style={{color: 'var(--upsc-gold)'}}>{children}</strong>,
                            ul: ({ children }) => <ul className="list-disc pl-4 space-y-1 mb-2">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal pl-4 space-y-1 mb-2">{children}</ol>,
                            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      msg.content
                    )}
                  </div>
                </div>
              ))}
              {isTyping && (
                <div className="msg-wrapper ai">
                  <div className="msg-bubble typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef}></div>
            </div>
          </main>

          <div className="chat-footer">
            <form className="input-group" onSubmit={handleChatSubmit}>
              <input
                ref={chatInputRef}
                type="text"
                placeholder="Ask your UPSC doubt..."
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                disabled={step === 5}
              />
              <button type="submit" className="btn-icon" disabled={!chatInput.trim() || step === 5}><Send size={20}/></button>
            </form>
          </div>

          {/* Overlay for Step 5 */}
          {step === 5 && (
            <div className="premium-overlay fade-in">
              <div className="overlay-card">
                <Star className="premium-icon" size={48} />
                <h2>You've used your free queries</h2>
                <p>Upgrade to continue unlocking master-level answers.</p>
                <button className="btn-premium" onClick={() => setStep(6)}>Unlock Full Access</button>
                <div className="subtext mt-3">Continue with unlimited answers, notes, and modes</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* STEP 6: UPGRADE SCREEN */}
      {step === 6 && (
        <div className="step-container upgrade-screen">
          <div className="card text-center fade-in upgrade-card">
             <div className="badge-pro">PRO EXPERT</div>
             <h1>Unlock Your True Potential</h1>
             <p className="subtext">Join 10,000+ top rankers using UPSC AI</p>

             <div className="benefits-list">
               <div className="benefit-item"><CheckCircle2 className="check" size={20} /> <span>Unlimited AI Answers</span></div>
               <div className="benefit-item"><CheckCircle2 className="check" size={20} /> <span>Prelims & Mains Modes</span></div>
               <div className="benefit-item"><CheckCircle2 className="check" size={20} /> <span>Smart Notes Saving</span></div>
               <div className="benefit-item"><CheckCircle2 className="check" size={20} /> <span>Daily Current Affairs Links</span></div>
             </div>

             <div className="price-tag">
               <span className="currency">₹</span>
               <span className="amount">499</span>
               <span className="duration">/month</span>
             </div>

             <button className="btn-primary w-full pulse-btn" onClick={() => setStep(7)}>Upgrade Now</button>
             <div className="payment-support mt-4">
                <p className="subtext xs">Supported: UPI, Cards, NetBanking</p>
                <p className="subtext xs font-bold">Instant access after payment</p>
             </div>
          </div>
        </div>
      )}

      {/* STEP 7: POWER MODE DASHBOARD */}
      {step === 7 && (
        <div className="step-container dashboard-layout fade-in">
           {/* Sidebar */}
            <aside className={`dash-sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`}>
               <div 
                 onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                 className="brand flex flex-col items-start gap-2 cursor-pointer hover:opacity-80 transition-opacity"
                 title={isSidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
               >
                 <Logo showText={false} className="h-10 w-auto" />
                 <span className="text-sm font-bold text-upsc-navy">{isSidebarCollapsed ? '' : "SELVA'S AI PRO"}</span>
               </div>
              <nav className="nav-links mt-6">
                <a href="#" className={activeView === 'chat' ? 'active' : ''} onClick={(e) => { e.preventDefault(); setActiveView('chat'); }}><MessageSquare size={18}/> <span>New Chat</span></a>
                <div className="subtext xs mt-4 mb-2 px-3" style={{color: 'var(--text-muted)'}}>RECENT CHATS</div>
                <a href="#" style={{opacity: 0.7}} onClick={(e) => { e.preventDefault(); setActiveView('chat'); }}><MessageSquare size={14}/> <span>Indus Valley Tech...</span></a>
                <a href="#" style={{opacity: 0.7}} onClick={(e) => { e.preventDefault(); setActiveView('chat'); }}><MessageSquare size={14}/> <span>Fundamental Rights vs...</span></a>
                <a href="#" style={{opacity: 0.7}} onClick={(e) => { e.preventDefault(); setActiveView('chat'); }}><MessageSquare size={14}/> <span>GDP calculation in...</span></a>
                <div className="subtext xs mt-4 mb-2 px-3" style={{color: 'var(--text-muted)'}}>RESOURCES</div>
                <a href="#" className={activeView === 'notes' ? 'active' : ''} onClick={(e) => { e.preventDefault(); setActiveView('notes'); }}><BookOpen size={18}/> <span>My Notes (12)</span></a>
                <a href="#" className={activeView === 'news' ? 'active' : ''} onClick={(e) => { e.preventDefault(); setActiveView('news'); }}><Newspaper size={18}/> <span>Daily News (Today)</span></a>
              </nav>
              <div className="user-profile mt-auto">
                <div className="avatar">{identityData.firstName ? identityData.firstName[0] : 'U'}</div>
                <div className="info">
                  <span className="name text-upsc-navy">{identityData.firstName || 'User'}</span>
                  <span className="plan">Pro Member</span>
                </div>
              </div>
           </aside>

           {/* Main Content */}
           <main className={`dash-main ${isSidebarCollapsed ? 'expanded' : ''}`}>
              <header className="dash-header">
                <div className="mode-toggle-group">
                   <button className={`mode-btn ${specialization === 'History' ? 'active' : ''}`} onClick={() => setSpecialization('History')}>History</button>
                   <button className={`mode-btn ${specialization === 'Anthropology' ? 'active' : ''}`} onClick={() => setSpecialization('Anthropology')}>Anthropology</button>
                   {showTooltip && (
                     <div className="mode-tooltip">
                       <div className="tooltip-arrow"></div>
                       Switch between your subjects
                     </div>
                   )}
                </div>
                <div className="header-actions">
                  <button className="action-btn" style={{background: activeView === 'notes' ? 'var(--bg-card)' : ''}} onClick={() => setActiveView('notes')}><BookOpen size={20}/></button>
                  <button className="action-btn" style={{background: activeView === 'news' ? 'var(--bg-card)' : ''}} onClick={() => setActiveView('news')}><Newspaper size={20}/></button>
                </div>
              </header>

              {activeView === 'chat' && (
                <>
                  <div className="dash-chat-area" style={{ flexDirection: 'column', justifyContent: 'flex-start', paddingBottom: '100px' }}>
                    <div className="messages-list w-full" style={{maxWidth: '800px', margin: '0 auto', marginTop: '20px'}}>
                      <div className="msg-wrapper user">
                        <div className="msg-bubble">Explain the significance of the Dandi March in India's freedom struggle.</div>
                      </div>
                      <div className="msg-wrapper ai">
                        <div className="msg-bubble">
                          <div className="formatted-content">
                            <strong>The Dandi March (Salt March) of 1930</strong><br/><br/>
                            1. <strong>Symbol of Mass Awakening:</strong> Salt, a basic necessity, was taxed by the British. Breaking the salt law united the masses irrespective of caste or class.<br/>
                            2. <strong>Launch of Civil Disobedience:</strong> It officially flagged off the Civil Disobedience Movement, moving the struggle from 'petition' to 'direct action'.<br/>
                            3. <strong>Global Attention:</strong> The peaceful march and subsequent arrests garnered international media coverage, exposing the harsh realities of British rule.
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div className="dash-footer">
                    <div className="input-group">
                      <input type="text" placeholder={`Ask your ${specialization} doubt...`} />
                      <button className="btn-icon"><Send size={20}/></button>
                    </div>
                  </div>
                </>
              )}

              {activeView === 'notes' && (
                <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
                  <h2 style={{ marginBottom: '24px' }}>My Saved Notes <span style={{fontSize: '1rem', color: 'var(--text-muted)'}}>({notes.length})</span></h2>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '800px' }}>
                    {notes.length === 0 ? (
                      <p className="text-gray-500">No saved notes yet.</p>
                    ) : (
                      notes.map(note => (
                        <div key={note.id} className="group relative" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border)' }}>
                          <button 
                            onClick={() => deleteNote(note.id)}
                            className="absolute top-4 right-4 p-2 text-gray-500 hover:text-red-500 bg-white/5 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                          >
                            <Trash2 size={16} />
                          </button>
                          <h3 style={{ marginTop: 0, fontSize: '0.9rem', color: 'var(--upsc-gold)' }}>Saved on {note.date}</h3>
                          <p style={{ color: 'var(--text-main)', margin: 0, fontSize: '1rem', lineHeight: '1.5' }}>{note.text}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {activeView === 'news' && (
                <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
                  <h2 style={{ marginBottom: '24px' }}>Daily Current Affairs <span style={{fontSize: '1rem', color: 'var(--text-muted)'}}>(Today)</span></h2>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '800px' }}>
                    <div style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border)' }}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                         <h3 style={{ marginTop: 0, marginBottom: '8px' }}>Supreme Court Verdict on Electoral Bonds</h3>
                         <span style={{ fontSize: '0.8rem', color: 'var(--bg-dark)', background: 'var(--primary)', padding: '4px 8px', borderRadius: '4px', fontWeight: 'bold' }}>Polity</span>
                      </div>
                      <p style={{ color: 'var(--text-muted)', margin: 0 }}>SC strikes down the scheme as unconstitutional, citing violation of right to information (Art 19(1)(a)).</p>
                    </div>
                    <div style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border)' }}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                         <h3 style={{ marginTop: 0, marginBottom: '8px' }}>India's New Space Station Plan</h3>
                         <span style={{ fontSize: '0.8rem', color: 'var(--bg-dark)', background: '#10B981', padding: '4px 8px', borderRadius: '4px', fontWeight: 'bold' }}>Science & Tech</span>
                      </div>
                      <p style={{ color: 'var(--text-muted)', margin: 0 }}>ISRO plans to set up 'Bharatiya Antariksha Station' by 2035 and send first Indian to moon by 2040.</p>
                    </div>
                  </div>
                </div>
              )}
           </main>
        </div>
      )}

    </div>
  );
};

export default MainFlow;
