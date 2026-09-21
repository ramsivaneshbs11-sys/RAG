import {
  MessageSquare, CheckSquare, Newspaper,
  LogIn, PanelLeftClose, PanelLeftOpen, ShieldCheck,
  LayoutDashboard, Upload, BookOpen, HardDrive, BookMarked, FileText
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import Logo from '../Logo';

// ── Menu items by role ────────────────────────────────────────────────────────
const STUDENT_MENU = [
  { name: 'Ask UPSC AI',    icon: MessageSquare, label: 'AI Chat' },
  { name: 'MCQ Practice AI', icon: CheckSquare,   label: 'MCQ'     },
  { name: 'Daily News',      icon: Newspaper,     label: 'News'    },
  { name: 'Quick Notes',     icon: BookMarked,    label: 'Notes'   },
];

const ADMIN_MENU = [
  { name: 'Admin Dashboard',    icon: LayoutDashboard, label: 'Dashboard'     },
  { name: 'PDF Ingestion',      icon: Upload,          label: 'Ingest'        },
  { name: 'Manage Documents',   icon: FileText,        label: 'Documents'     },
  { name: 'Syllabus Manager',   icon: BookOpen,        label: 'Syllabus'      },
  { name: 'Cache & Storage',    icon: HardDrive,       label: 'Cache'         },
];

const Sidebar = () => {
  const {
    activeTab, setActiveTab,
    setIsLoginModalOpen,
    isSidebarCollapsed, setIsSidebarCollapsed,
    userRole, user, logout
  } = useApp();

  const isAdmin = userRole === 'admin';
  const menuItems = isAdmin ? ADMIN_MENU : STUDENT_MENU;

  const handleTabClick = (name) => {
    setActiveTab(name);
  };

  const isItemActive = (name) => {
    return activeTab === name;
  };

  return (
    <div className={`${isSidebarCollapsed ? 'w-20' : 'w-72'} h-screen flex flex-col bg-[var(--bg-card)] rounded-none border-r border-[var(--border-color)] p-4 sticky top-0 transition-all duration-300 ease-in-out z-50`}>

      {/* Header: Logo + Collapse Toggle */}
      {isSidebarCollapsed ? (
        <div className="flex flex-col items-center gap-2 mb-6 border-b border-[var(--border-color)] pb-3">
          <Logo showText={false} className="h-8 w-auto" />
          <button
            onClick={() => setIsSidebarCollapsed(false)}
            className="p-1.5 rounded-xl bg-upsc-navy/5 hover:bg-upsc-navy/10 text-upsc-navy transition-all hover:scale-105 active:scale-95 shadow-sm group relative"
            title="Expand Sidebar"
          >
            <PanelLeftOpen size={18} className="text-upsc-navy" />
            <span className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-[#0f2242] text-white text-[10px] font-bold rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-md z-[100]">
              Expand Sidebar
            </span>
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between mb-6 px-1 border-b border-[var(--border-color)] pb-3">
          <Logo showText={true} className="h-9 w-auto" />
          <button
            onClick={() => setIsSidebarCollapsed(true)}
            className="p-1.5 text-gray-400 hover:text-upsc-navy hover:bg-black/5 rounded-xl transition-all active:scale-95"
            title="Collapse Sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
      )}

      {/* Role Badge */}
      {!isSidebarCollapsed && (
        <div className={`mb-3 px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-widest text-center ${
          isAdmin
            ? 'bg-upsc-maroon/10 text-upsc-maroon border border-upsc-maroon/20'
            : 'bg-upsc-navy/5 text-upsc-navy/70 border border-upsc-navy/20'
        }`}>
          {isAdmin ? '🛡️ Admin Portal' : '🎓 Student Portal'}
        </div>
      )}

      {/* Menu Items */}
      <div className="flex-1 space-y-1.5 mt-2">
        <p className={`text-[9px] font-bold text-gray-400 uppercase tracking-widest px-3 mb-3 ${isSidebarCollapsed ? 'text-center' : ''}`}>
          {isSidebarCollapsed ? (isAdmin ? 'ADM' : 'AI') : (isAdmin ? 'Admin Tools' : 'AI Tools')}
        </p>

        {menuItems.map((item) => (
          <div
            key={item.name}
            onClick={() => handleTabClick(item.name)}
            className={`sidebar-item ${isItemActive(item.name) ? 'active' : ''} ${isSidebarCollapsed ? 'justify-center px-0' : 'px-3'}`}
            title={isSidebarCollapsed ? item.name : ''}
          >
            <item.icon size={18} />
            {!isSidebarCollapsed && <span className="text-xs font-semibold fade-in">{item.name}</span>}
          </div>
        ))}
      </div>

      {/* User Profile Section */}
      <div className={`mt-auto pt-4 border-t border-[var(--border-color)] ${isSidebarCollapsed ? 'px-0' : 'px-2'}`}>
        {user ? (
          <div className="flex flex-col gap-3">
            <div className={`flex items-center gap-3 ${isSidebarCollapsed ? 'justify-center' : ''}`}>
              <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold border shrink-0 ${
                isAdmin
                  ? 'bg-upsc-maroon/20 text-upsc-maroon border-upsc-maroon/30'
                  : 'bg-upsc-gold/20 text-upsc-gold border-upsc-gold/30'
              }`}>
                {isAdmin ? <ShieldCheck size={18} /> : (user?.name?.charAt(0)?.toUpperCase() || 'U')}
              </div>
              {!isSidebarCollapsed && (
                <div className="flex flex-col overflow-hidden">
                  <span className="text-sm font-bold text-[var(--text-main)] truncate">{user.name}</span>
                  <span className={`text-[10px] uppercase tracking-tighter font-bold ${isAdmin ? 'text-upsc-maroon' : 'text-upsc-gold'}`}>
                    {isAdmin ? 'Administrator' : (user.plan || 'Free') + ' Plan'}
                  </span>
                </div>
              )}
            </div>

            <button
              onClick={() => { logout(); window.location.href = '/login'; }}
              className={`flex items-center gap-2 py-2 px-3 rounded-lg text-[var(--text-muted)] hover:text-red-600 hover:bg-red-50 transition-all group ${isSidebarCollapsed ? 'justify-center' : ''}`}
              title={isSidebarCollapsed ? 'Logout' : ''}
            >
              <LogIn size={18} className="group-hover:text-red-600 transition-colors" />
              {!isSidebarCollapsed && <span className="text-sm font-medium">Logout</span>}
            </button>
          </div>
        ) : (
          <button
            onClick={() => setIsLoginModalOpen(true)}
            className={`flex items-center gap-2 py-2 px-3 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-all ${isSidebarCollapsed ? 'justify-center' : ''}`}
          >
            <LogIn size={18} />
            {!isSidebarCollapsed && <span className="text-sm font-medium">Login</span>}
          </button>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
