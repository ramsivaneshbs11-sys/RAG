import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';

/**
 * ConfirmDialog — Replaces window.confirm() with a styled in-app modal.
 * Usage:
 *   const [confirm, setConfirm] = useState(null);
 *   <ConfirmDialog config={confirm} onClose={() => setConfirm(null)} />
 *   setConfirm({ message: 'Are you sure?', onConfirm: () => doSomething() });
 */
const ConfirmDialog = ({ config, onClose }) => {
  if (!config) return null;

  const handleConfirm = () => {
    config.onConfirm?.();
    onClose();
  };

  return (
    <AnimatePresence>
      {config && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
          onClick={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 10 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="bg-white rounded-3xl shadow-2xl p-6 w-full max-w-sm border border-gray-100"
          >
            {/* Icon */}
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-2xl bg-red-50 flex items-center justify-center shrink-0">
                <AlertTriangle size={20} className="text-red-500" />
              </div>
              <h3 className="text-base font-black text-[#0f2242]">
                {config.title || 'Confirm Action'}
              </h3>
              <button
                onClick={onClose}
                className="ml-auto p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition-all"
              >
                <X size={16} />
              </button>
            </div>

            {/* Message */}
            <p className="text-sm text-gray-600 leading-relaxed mb-6 pl-1">
              {config.message || 'Are you sure you want to proceed?'}
            </p>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-2.5 rounded-xl border border-gray-200 text-gray-600 font-bold text-sm hover:bg-gray-50 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                className="flex-1 py-2.5 rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold text-sm transition-all shadow-md shadow-red-500/20 active:scale-95"
              >
                {config.confirmLabel || 'Delete'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ConfirmDialog;
