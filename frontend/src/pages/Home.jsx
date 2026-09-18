import React, { useState, Suspense, lazy } from 'react';
import Sidebar from '../components/layout/Sidebar';
import RightSidebar from '../components/layout/RightSidebar';
import Dashboard from '../components/dashboard/Dashboard';
import ChatInterface from '../components/tools/ChatInterface';
import LoginModal from '../components/auth/LoginModal';
import BottomNavigation from '../components/layout/BottomNavigation';
import MobileChat from '../components/tools/MobileChat';
import MobileProfile from '../components/tools/MobileProfile';
import { useApp } from '../context/AppContext';
import { AnimatePresence, motion } from 'framer-motion';
import { Plus, Trash2, FileText, Edit3 } from 'lucide-react';

const MCQPractice = lazy(() => import('../components/tools/MCQPractice'));
const DailyNews = lazy(() => import('../components/tools/DailyNews'));
const AdminPanel = lazy(() => import('../components/tools/AdminPanel'));

const Home = () => {
  const { activeTab, isLoginModalOpen, setIsLoginModalOpen, notes, addNote, deleteNote, updateNote } = useApp();
  const [noteInput, setNoteInput] = React.useState('');
  const [isAddingNote, setIsAddingNote] = React.useState(false);
  const [editingId, setEditingId] = React.useState(null);
  const [editText, setEditText] = React.useState('');

  const handleSaveNote = () => {
    if (noteInput.trim()) {
      addNote(noteInput);
      setNoteInput('');
      setIsAddingNote(false);
    }
  };

  const handleUpdateNote = (id) => {
    if (editText.trim()) {
      updateNote(id, editText);
      setEditingId(null);
    }
  };

  const handleDeleteNote = (id) => {
    if (window.confirm('Do you want to delete this note?')) {
      deleteNote(id);
    }
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'Ask UPSC AI':
        return (
          <>
            <div className="hidden md:block h-full"><ChatInterface /></div>
            <div className="block md:hidden h-full"><MobileChat /></div>
          </>
        );
      case 'MCQ Practice AI':
        return <MCQPractice />;
      case 'Daily News':
        return <DailyNews />;
      // Admin tabs
      case 'Admin Dashboard':
        return <AdminPanel initialTab={0} />;
      case 'Admin Panel':
        return <AdminPanel initialTab={1} />;
      case 'Quick Notes':
        return (
          <div className="block md:hidden p-6 pb-40">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-3xl font-black text-upsc-navy">Quick Notes</h2>
              <button 
                onClick={() => setIsAddingNote(!isAddingNote)}
                className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg active:scale-90 transition-all ${
                  isAddingNote ? 'bg-red-50 text-red-500' : 'bg-upsc-navy text-white'
                }`}
              >
                {isAddingNote ? <Plus size={24} className="rotate-45" /> : <Plus size={24} />}
              </button>
            </div>

            <AnimatePresence>
              {isAddingNote && (
                <motion.div 
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mb-8 overflow-hidden"
                >
                  <div className="bg-white border-2 border-upsc-navy/10 p-5 rounded-[28px] shadow-xl">
                    <textarea
                      value={noteInput}
                      onChange={(e) => setNoteInput(e.target.value)}
                      placeholder="Write your study note here..."
                      className="w-full h-32 bg-transparent border-none focus:ring-0 text-sm font-medium text-slate-700 placeholder:text-slate-300 resize-none"
                      autoFocus
                    />
                    <div className="flex justify-end gap-3 mt-4">
                      <button 
                        onClick={() => setIsAddingNote(false)}
                        className="px-6 py-3 text-xs font-bold text-slate-400 uppercase tracking-widest"
                      >
                        Cancel
                      </button>
                      <button 
                        onClick={handleSaveNote}
                        disabled={!noteInput.trim()}
                        className="px-8 py-3 bg-upsc-navy text-white rounded-xl text-xs font-bold uppercase tracking-widest shadow-lg shadow-upsc-navy/20 disabled:opacity-50"
                      >
                        Save Note
                      </button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="space-y-4">
              {notes.length === 0 ? (
                <div className="text-center py-20 bg-white rounded-[32px] border-2 border-dashed border-slate-100 flex flex-col items-center">
                  <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-4">
                    <FileText className="text-slate-200" size={32} />
                  </div>
                  <p className="text-slate-400 font-bold">No notes yet.</p>
                  <p className="text-[10px] text-slate-300 uppercase tracking-widest mt-1">Start writing your UPSC ideas</p>
                </div>
              ) : (
                notes.map(note => (
                  <motion.div 
                    layout
                    key={note.id} 
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="p-5 bg-white border border-slate-100 rounded-[28px] shadow-sm relative group"
                  >
                    <div className="absolute top-4 right-4 flex gap-2">
                      <button 
                        onClick={() => {
                          setEditingId(note.id);
                          setEditText(note.text);
                        }}
                        className="p-2 text-slate-300 hover:text-upsc-navy hover:bg-upsc-navy/5 rounded-xl transition-all"
                      >
                        <Edit3 size={16} />
                      </button>
                      <button 
                        onClick={() => handleDeleteNote(note.id)}
                        className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>

                    {editingId === note.id ? (
                      <div className="mt-2">
                        <textarea
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          className="w-full bg-slate-50 border border-slate-100 rounded-2xl p-4 text-sm font-medium text-slate-700 focus:outline-none focus:border-upsc-navy/30 h-32"
                          autoFocus
                        />
                        <div className="flex justify-end gap-3 mt-4">
                          <button onClick={() => setEditingId(null)} className="px-4 py-2 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Cancel</button>
                          <button onClick={() => handleUpdateNote(note.id)} className="px-6 py-2 text-[10px] font-bold bg-upsc-navy text-white rounded-xl uppercase tracking-widest">Save</button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="text-sm font-medium text-slate-700 leading-relaxed mb-4 pr-16 whitespace-pre-wrap">{note.text}</p>
                        <div className="flex items-center gap-2">
                          <div className="w-1.5 h-1.5 bg-upsc-gold rounded-full"></div>
                          <p className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">{note.date}</p>
                        </div>
                      </>
                    )}
                  </motion.div>
                ))
              )}
            </div>
          </div>
        );
      case 'Profile':
        return <MobileProfile />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="flex min-h-screen bg-[var(--bg-dark)]">
      {/* Desktop Sidebar */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Main Content Area */}
      <main className="flex-1 min-h-screen overflow-x-hidden">
          <Suspense fallback={
            <div className="flex-1 flex items-center justify-center p-12">
              <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-upsc-navy"></div>
            </div>
          }>
            {renderContent()}
          </Suspense>
      </main>

      {/* Desktop Right Sidebar (Notes) */}
      <div className="hidden md:block">
        <RightSidebar />
      </div>

      {/* Mobile Bottom Navigation */}
      <BottomNavigation />

      {/* Global Modals */}
      <LoginModal isOpen={isLoginModalOpen} onClose={() => setIsLoginModalOpen(false)} />
    </div>
  );
};

export default Home;
