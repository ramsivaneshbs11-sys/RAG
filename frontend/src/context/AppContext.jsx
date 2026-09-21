import React, { createContext, useContext, useState, useEffect } from 'react';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [activeTab, setActiveTab] = useState('Ask UPSC AI');
  const [chatHistory, setChatHistory] = useState([]);
  const [selectedSubject, setSelectedSubject] = useState('History');
  const [chatInput, setChatInput] = useState('');
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [chatMode, setChatMode] = useState('prelims'); // 'prelims' | 'mains' | 'current_affairs'

  // ── Role-based auth ('student' | 'admin') ─────────────────────────────────
  const [userRole, setUserRole] = useState(() => {
    return localStorage.getItem('upsc_role') || 'student';
  });

  const [user, setUser] = useState(() => {
    const savedUser = localStorage.getItem('upsc_user');
    return savedUser ? JSON.parse(savedUser) : { name: 'UPSC Aspirant', plan: 'Free' };
  });

  const [isLoggedIn, setIsLoggedIn] = useState(() => !!localStorage.getItem('upsc_user'));
  const [notes, setNotes] = useState(() => {
    const savedNotes = localStorage.getItem('upsc_notes');
    return savedNotes ? JSON.parse(savedNotes) : [];
  });

  const login = (userData, role = 'student') => {
    setUser(userData);
    setUserRole(role);
    setIsLoggedIn(true);
    localStorage.setItem('upsc_user', JSON.stringify(userData));
    localStorage.setItem('upsc_role', role);
    // Default landing tab based on role
    if (role === 'admin') {
      setActiveTab('Admin Dashboard');
    } else {
      setActiveTab('Ask UPSC AI');
    }
  };

  const logout = () => {
    setUser(null);
    setUserRole('student');
    setIsLoggedIn(false);
    localStorage.removeItem('upsc_user');
    localStorage.removeItem('upsc_role');
    setActiveTab('Ask UPSC AI');
  };

  useEffect(() => {
    localStorage.setItem('upsc_notes', JSON.stringify(notes));
  }, [notes]);

  const addNote = (content) => {
    const newNote = {
      id: Date.now(),
      text: content,
      date: new Date().toLocaleDateString()
    };
    setNotes([newNote, ...notes]);
  };

  const deleteNote = (id) => {
    setNotes(notes.filter(note => note.id !== id));
  };

  const updateNote = (id, newText) => {
    setNotes(notes.map(note =>
      note.id === id ? { ...note, text: newText, lastModified: new Date().toLocaleDateString() } : note
    ));
  };

  const addChatMessage = (message) => {
    setChatHistory(prev => [...prev, message]);
  };

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  return (
    <AppContext.Provider value={{
      activeTab, setActiveTab,
      chatHistory, setChatHistory, addChatMessage,
      selectedSubject, setSelectedSubject,
      chatInput, setChatInput,
      chatMode, setChatMode,
      notes, addNote, deleteNote, updateNote,
      isLoginModalOpen, setIsLoginModalOpen,
      isSidebarCollapsed, setIsSidebarCollapsed,
      userRole, setUserRole,
      user, setUser, isLoggedIn, login, logout
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => useContext(AppContext);
