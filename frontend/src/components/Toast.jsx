/**
 * Toast — top-right success notification, auto-dismisses after `duration` ms.
 * Uses a React portal so it always renders above all other content.
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

function ToastContent({ message, sub, duration = 5500, onDismiss }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const show = setTimeout(() => setVisible(true), 20);
    const hide = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 300);
    }, duration);
    return () => { clearTimeout(show); clearTimeout(hide); };
  }, []); // eslint-disable-line

  return (
    <div
      className={`fixed top-5 right-5 z-[99999] flex items-start gap-3 bg-white border border-green-200 shadow-xl rounded-xl px-4 py-3.5 w-[300px] transition-all duration-300
        ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-3 pointer-events-none'}`}
      role="alert"
      aria-live="polite"
    >
      {/* Icon */}
      <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0 mt-0.5">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#16a34a" strokeWidth="2" strokeLinecap="round">
          <circle cx="8" cy="8" r="6" />
          <polyline points="5 8.5 7 10.5 11 6" />
        </svg>
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-bold text-gray-900 leading-snug">{message}</p>
        {sub && <p className="text-[12px] font-medium text-gray-500 mt-0.5 leading-snug">{sub}</p>}
      </div>

      {/* Close */}
      <button
        onClick={() => { setVisible(false); setTimeout(onDismiss, 300); }}
        className="text-gray-400 hover:text-gray-600 flex-shrink-0 mt-0.5 transition-colors"
        aria-label="Dismiss"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="4" y1="4" x2="12" y2="12" /><line x1="12" y1="4" x2="4" y2="12" />
        </svg>
      </button>
    </div>
  );
}

export default function Toast(props) {
  return createPortal(<ToastContent {...props} />, document.body);
}
