import React, { useState } from 'react';
import { Plus, Trash2, Edit3, X, FileText, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { motion, AnimatePresence } from 'framer-motion';
import ConfirmDialog from '../ui/ConfirmDialog';

const NotesPanel = () => {
  const { notes, addNote, deleteNote, updateNote } = useApp();
  const [isOpen, setIsOpen] = useState(true);
  const [newNote, setNewNote] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [confirmDialog, setConfirmDialog] = useState(null);

  const handleAdd = () => {
    if (newNote.trim()) {
      addNote(newNote);
      setNewNote('');
      setIsAdding(false);
    }
  };

  const handleUpdate = (id) => {
    if (editText.trim()) {
      updateNote(id, editText);
      setEditingId(null);
    }
  };

  const handleDelete = (id) => {
    setConfirmDialog({
      title: 'Delete Note',
      message: 'Are you sure you want to delete this note? This action cannot be undone.',
      confirmLabel: 'Delete',
      onConfirm: () => deleteNote(id),
    });
  };

  // Collapsed Sidebar View
  if (!isOpen) {
    return (
      <div className="w-14 h-screen sticky top-0 border-l border-[var(--border-color)] bg-[var(--bg-card)] flex flex-col items-center py-6 px-2 shadow-sm transition-all duration-300 shrink-0">
        <button
          onClick={() => setIsOpen(true)}
          className="p-2.5 rounded-xl bg-upsc-navy/5 hover:bg-upsc-navy/10 text-upsc-navy transition-all hover:scale-105 active:scale-95 shadow-sm group relative"
          title="Expand Quick Notes"
        >
          <PanelRightOpen size={20} className="text-upsc-navy" />
          {notes.length > 0 && (
            <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-[9px] font-black w-4 h-4 rounded-full flex items-center justify-center shadow">
              {notes.length}
            </span>
          )}
          <span className="absolute right-full mr-2 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-[#0f2242] text-white text-[10px] font-bold rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-md">
            Expand Quick Notes
          </span>
        </button>
      </div>
    );
  }

  // Expanded Sidebar View
  return (
    <div className="w-80 h-screen flex flex-col p-6 sticky top-0 border-l border-[var(--border-color)] bg-[var(--bg-card)] shadow-2xl transition-all duration-300 shrink-0">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[var(--border-color)]">
        <h2 className="text-xl font-bold flex items-center gap-2 text-upsc-navy">
          <FileText className="text-upsc-gold" size={20} />
          Quick Notes
        </h2>
        <div className="flex items-center gap-1">
          <button 
            onClick={() => setIsAdding(!isAdding)}
            className="p-2 bg-upsc-gold/10 text-upsc-gold rounded-xl hover:bg-upsc-gold/20 transition-all active:scale-95"
            title="Add Note"
          >
            <Plus size={18} />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 text-gray-400 hover:text-upsc-navy hover:bg-black/5 rounded-xl transition-all active:scale-95"
            title="Collapse Notes Panel"
          >
            <PanelRightClose size={20} />
          </button>
        </div>
      </div>

      <AnimatePresence>
        {isAdding && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="mb-6 p-4 bg-[var(--bg-dark)] border border-[var(--border-color)] rounded-2xl shadow-xl transition-colors"
          >
            <textarea
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              placeholder="Jot down something important..."
              className="w-full bg-transparent border-none focus:ring-0 text-sm resize-none h-24 text-[var(--text-main)] placeholder:text-gray-400"
              autoFocus
            />
            <div className="flex justify-end gap-2 mt-2">
              <button onClick={() => setIsAdding(false)} className="px-3 py-1 text-xs text-gray-500 hover:bg-black/5 rounded-md">Cancel</button>
              <button onClick={handleAdd} className="px-3 py-1 text-xs bg-upsc-navy text-white rounded-md hover:bg-opacity-90 font-medium">Save Note</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4">
        {notes.length === 0 && !isAdding && (
          <div className="text-center py-10">
            <div className="w-12 h-12 bg-black/5 rounded-full flex items-center justify-center mx-auto mb-4">
              <FileText className="text-gray-300" />
            </div>
            <p className="text-sm text-[var(--text-muted)]">No notes yet. Start writing ideas for your UPSC prep!</p>
          </div>
        )}
        {notes.map((note) => (
          <motion.div
            layout
            key={note.id}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="p-4 bg-[var(--bg-dark)] border border-[var(--border-color)] rounded-2xl group relative transition-colors"
          >
            <div className="absolute top-3 right-3 flex gap-1">
              <button 
                onClick={() => {
                  setEditingId(note.id);
                  setEditText(note.text);
                }}
                className="p-1.5 text-gray-500 hover:text-upsc-navy hover:bg-upsc-navy/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                title="Edit Note"
              >
                <Edit3 size={14} />
              </button>
              <button 
                onClick={() => handleDelete(note.id)}
                className="p-1.5 text-gray-500 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                title="Delete Note"
              >
                <Trash2 size={14} />
              </button>
            </div>

            {editingId === note.id ? (
              <div className="pt-2">
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="w-full bg-white/50 border border-upsc-navy/20 rounded-xl p-3 text-sm mb-2 focus:outline-none focus:border-upsc-navy/50 h-24"
                  autoFocus
                />
                <div className="flex justify-end gap-2">
                  <button onClick={() => setEditingId(null)} className="px-3 py-1 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Cancel</button>
                  <button onClick={() => handleUpdate(note.id)} className="px-4 py-1 text-[10px] font-bold bg-upsc-navy text-white rounded-lg uppercase tracking-widest">Save</button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-sm text-[var(--text-main)] whitespace-pre-wrap leading-relaxed pr-8">{note.text}</p>
                <div className="mt-3 text-[10px] text-gray-400 font-medium">Saved on {note.date}</div>
              </>
            )}
          </motion.div>
        ))}
      </div>
      <ConfirmDialog config={confirmDialog} onClose={() => setConfirmDialog(null)} />
    </div>
  );
};

export default NotesPanel;
