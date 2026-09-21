import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Languages, BookOpen, ArrowRight, ArrowLeft, User, Star } from 'lucide-react';
import { useApp } from '../context/AppContext';
import './Onboarding.css';

const Onboarding = () => {
  const { login } = useApp();
  const [step, setStep] = useState(1);
  const [preferences, setPreferences] = useState({
    name: '',
    language: 'English',
    subject: 'History',
    plan: ''
  });
  
  const navigate = useNavigate();

  useEffect(() => {
    document.title = 'Setup Your Profile | UPSC AI';
  }, []);

  useEffect(() => {
    const tempPhone = localStorage.getItem('upsc_temp_phone');
    if (!tempPhone) {
      navigate('/');
    }
  }, [navigate]);

  const handleSelection = (key, value) => {
    setPreferences({ ...preferences, [key]: value });
  };

  const nextStep = () => {
    if (step < 2) setStep(step + 1);
    else {
      const phone = localStorage.getItem('upsc_temp_phone');
      const userData = {
        ...preferences,
        phone,
        joinedAt: new Date().toISOString()
      };
      
      // Save to mock database
      const registeredUsers = JSON.parse(localStorage.getItem('upsc_registered_users') || '[]');
      // Update if exists, otherwise add
      const userIndex = registeredUsers.findIndex(u => u.phone === phone);
      if (userIndex > -1) {
        registeredUsers[userIndex] = userData;
      } else {
        registeredUsers.push(userData);
      }
      localStorage.setItem('upsc_registered_users', JSON.stringify(registeredUsers));

      login(userData);
      localStorage.removeItem('upsc_temp_phone');
      navigate('/home');
    }
  };

  const prevStep = () => {
    if (step > 1) setStep(step - 1);
  };

  return (
    <div className="page-container onboarding-page">
      <div className="onboarding-box glass-panel">
        
        {/* Progress header */}
        <div className="onboarding-progress">
          <div className={`progress-dot ${step >= 1 ? 'active' : ''}`}></div>
          <div className="progress-line"></div>
          <div className={`progress-dot ${step >= 2 ? 'active' : ''}`}></div>
        </div>

        {step === 1 && (
          <div className="step-content fade-in">
            <User size={40} className="step-icon" />
            <h2>What's your name?</h2>
            <p className="step-desc">Let's personalize your UPSC preparation journey.</p>
            
            <div className="input-group-onboarding">
              <input 
                type="text" 
                placeholder="Enter your full name" 
                className="onboarding-input"
                value={preferences.name}
                onChange={(e) => handleSelection('name', e.target.value)}
                autoFocus
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="step-content fade-in">
            <Star size={40} className="step-icon" />
            <h2>Select your Plan</h2>
            <p className="step-desc">Choose a plan that fits your preparation needs.</p>
            
            <div className="card-grid">
              <div 
                className={`choice-card ${preferences.plan === 'Free' ? 'selected' : ''}`}
                onClick={() => handleSelection('plan', 'Free')}
              >
                <h3>Free Plan</h3>
                <p className="text-[10px] text-gray-400 mt-2">Basic AI access</p>
              </div>
              <div 
                className={`choice-card ${preferences.plan === 'Pro' ? 'selected' : ''}`}
                onClick={() => handleSelection('plan', 'Pro')}
              >
                <div className="flex items-center justify-center gap-1">
                  <Star size={14} className="text-upsc-gold" />
                  <h3>Pro Plan</h3>
                </div>
                <p className="text-[10px] text-gray-400 mt-2">Unlimited AI & Mock Tests</p>
              </div>
            </div>
          </div>
        )}

        <div className="onboarding-footer">
          {step > 1 ? (
            <button className="btn-secondary flex-center" onClick={prevStep}>
              <ArrowLeft size={18} style={{marginRight: '8px'}} /> Back
            </button>
          ) : <div></div>}
          
          <button 
            className="btn-primary flex-center" 
            onClick={nextStep}
            disabled={
              (step === 1 && !preferences.name) || 
              (step === 2 && !preferences.plan)
            }
          >
            {step === 2 ? 'Get Started' : 'Next'} <ArrowRight size={18} style={{marginLeft: '8px'}} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Onboarding;
