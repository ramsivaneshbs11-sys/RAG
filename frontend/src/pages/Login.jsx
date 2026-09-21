import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Phone, ArrowRight, ShieldCheck, ChevronLeft, Lock, GraduationCap, KeyRound } from 'lucide-react';
import Logo from '../components/Logo';
import { motion, AnimatePresence } from 'framer-motion';
import { useApp } from '../context/AppContext';
import './Login.css';

// Admin password (in production, validate via backend)
const ADMIN_PASSWORD = import.meta.env.VITE_ADMIN_PASSWORD || 'admin123';

// ── StudentLogin ──────────────────────────────────────────────────────────────
const StudentLogin = ({ onLogin }) => {
  const [step, setStep] = useState(1);
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState(['', '', '', '']);
  const otpRefs = useRef([]);

  const handleOtpChange = (index, value) => {
    if (isNaN(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);
    if (value !== '' && index < 3) otpRefs.current[index + 1]?.focus();
  };

  const handleOtpKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (phone.length === 10) setStep(2);
  };

  const handleVerify = (e) => {
    e.preventDefault();
    if (otp.every(v => v !== '')) {
      const registeredUsers = JSON.parse(localStorage.getItem('upsc_registered_users') || '[]');
      const existing = registeredUsers.find(u => u.phone === phone);
      onLogin(existing && existing.name ? existing : { name: 'UPSC Aspirant', plan: 'Free', phone }, 'student', existing && existing.name ? 'home' : 'onboarding');
    }
  };

  return (
    <AnimatePresence mode="wait">
      {step === 1 ? (
        <motion.form key="step1" className="login-form" onSubmit={handleSend}
          initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
          <div className="input-group">
            <Phone size={18} className="input-icon" />
            <input
              type="tel" placeholder="Enter Phone Number" className="input-field"
              value={phone} maxLength={10} autoFocus
              onChange={e => { const v = e.target.value.replace(/\D/g, ''); if (v.length <= 10) setPhone(v); }}
              required
            />
          </div>
          <button type="submit" className="btn-primary full-width mt-4 group" disabled={phone.length !== 10}>
            Generate OTP <ArrowRight size={18} className="ml-2 group-hover:translate-x-1 transition-transform" />
          </button>
          <p className="text-center text-[10px] text-gray-500 uppercase tracking-widest mt-6">
            Protected by UPSC AI Secure Gateway
          </p>
        </motion.form>
      ) : (
        <motion.form key="step2" className="login-form" onSubmit={handleVerify}
          initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
          <div className="text-center mb-6">
            <div className="w-16 h-16 bg-upsc-gold/10 rounded-full flex items-center justify-center text-upsc-gold mx-auto mb-4">
              <ShieldCheck size={32} />
            </div>
            <p className="text-sm text-gray-300">
              Enter the 4-digit code sent to<br />
              <span className="text-upsc-gold font-bold">{phone}</span>
            </p>
          </div>
          <div className="otp-container">
            {otp.map((val, i) => (
              <input key={i} ref={el => otpRefs.current[i] = el}
                type="text" maxLength={1} className="otp-box" value={val} autoFocus={i === 0}
                onChange={e => handleOtpChange(i, e.target.value)}
                onKeyDown={e => handleOtpKeyDown(i, e)}
              />
            ))}
          </div>
          <button type="submit" className="btn-primary full-width mt-4">
            Verify &amp; Login
          </button>
          <div className="flex justify-between items-center mt-6">
            <button type="button" className="flex items-center gap-1 text-xs text-gray-500 hover:text-white transition-colors" onClick={() => setStep(1)}>
              <ChevronLeft size={14} /> Change Number
            </button>
            <button type="button" className="btn-text">Resend OTP</button>
          </div>
        </motion.form>
      )}
    </AnimatePresence>
  );
};

// ── AdminLogin ────────────────────────────────────────────────────────────────
const AdminLogin = ({ onLogin }) => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (password === ADMIN_PASSWORD) {
      onLogin({ name: 'Admin', plan: 'Admin', role: 'admin' }, 'admin', 'home');
    } else {
      setError('Invalid admin password. Please try again.');
      setPassword('');
    }
  };

  return (
    <motion.form className="login-form" onSubmit={handleSubmit}
      initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
      <div className="text-center mb-6">
        <div className="w-16 h-16 bg-upsc-maroon/10 rounded-full flex items-center justify-center text-upsc-maroon mx-auto mb-4">
          <KeyRound size={28} />
        </div>
        <p className="text-sm text-gray-300">Enter Admin Access Key to continue</p>
      </div>

      <div className="input-group">
        <Lock size={18} className="input-icon" />
        <input
          type="password" placeholder="Admin Password" className="input-field"
          value={password} autoFocus
          onChange={e => { setPassword(e.target.value); setError(''); }}
          required
        />
      </div>

      {error && (
        <motion.p className="text-red-400 text-xs text-center mt-2 font-medium"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          {error}
        </motion.p>
      )}

      <button type="submit" className="btn-primary full-width mt-4 group" disabled={!password}>
        Access Admin Portal <ArrowRight size={18} className="ml-2 group-hover:translate-x-1 transition-transform" />
      </button>
      <p className="text-center text-[10px] text-gray-500 uppercase tracking-widest mt-6">
        Admin access is restricted and monitored
      </p>
    </motion.form>
  );
};

// ── Main Login ────────────────────────────────────────────────────────────────
const Login = () => {
  const { login } = useApp();
  const navigate = useNavigate();
  const [roleTab, setRoleTab] = useState('student'); // 'student' | 'admin'

  React.useEffect(() => {
    document.title = 'Login | UPSC AI';
  }, []);

  const handleLogin = (userData, role, destination) => {
    login(userData, role);
    if (destination === 'onboarding') {
      localStorage.setItem('upsc_temp_phone', userData.phone);
      navigate('/onboarding');
    } else {
      navigate('/home');
    }
  };

  return (
    <div className="login-page">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="login-box"
      >
        {/* Header */}
        <div className="login-header">
          <div className="flex justify-center mb-2 transform scale-90 md:scale-100">
            <Logo showText={true} />
          </div>
          <p className="font-medium text-slate-500">Choose your access mode to continue</p>
        </div>

        {/* Role Toggle Tabs */}
        <div className="flex gap-2 p-1 bg-gray-100 rounded-2xl mb-6">
          <button
            type="button"
            onClick={() => setRoleTab('student')}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold transition-all ${
              roleTab === 'student'
                ? 'bg-white text-upsc-navy shadow-sm'
                : 'text-gray-500 hover:text-upsc-navy'
            }`}
          >
            <GraduationCap size={15} />
            Student Login
          </button>
          <button
            type="button"
            onClick={() => setRoleTab('admin')}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold transition-all ${
              roleTab === 'admin'
                ? 'bg-white text-upsc-maroon shadow-sm'
                : 'text-gray-500 hover:text-upsc-maroon'
            }`}
          >
            <ShieldCheck size={15} />
            Admin Login
          </button>
        </div>

        {/* Role Content */}
        <AnimatePresence mode="wait">
          {roleTab === 'student' ? (
            <motion.div key="student"
              initial={{ opacity: 0, x: 15 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -15 }} transition={{ duration: 0.25 }}>
              <StudentLogin onLogin={handleLogin} />
            </motion.div>
          ) : (
            <motion.div key="admin"
              initial={{ opacity: 0, x: 15 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -15 }} transition={{ duration: 0.25 }}>
              <AdminLogin onLogin={handleLogin} />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
};

export default Login;
