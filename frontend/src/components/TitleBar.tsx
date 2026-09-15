import React, { useState, useEffect, useRef } from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useStore } from '../store';
import TabBar from './TabBar';

export const TitleBar: React.FC = () => {
  const { theme, toggleTheme, openTab, setIsSettingsOpen } = useStore();
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!('__TAURI_INTERNALS__' in window)) return;

    const appWindow = getCurrentWindow();
    let isCancelled = false;

    const checkFullscreen = async () => {
      // 1. Instant check: A windowed (non-fullscreen) window on macOS cannot take the full screen width.
      // If the window width is less than screen width - 50px, it is guaranteed to be windowed.
      const isNarrowerThanScreen = window.innerWidth < (window.screen.width - 50);
      if (isNarrowerThanScreen) {
        if (!isCancelled) {
          setIsFullscreen(false);
          document.body.dataset.windowFullscreen = 'false';
        }
        return;
      }

      // 2. Full width: verify using native Tauri API
      try {
        const fs = await appWindow.isFullscreen();
        if (!isCancelled) {
          setIsFullscreen(fs);
          document.body.dataset.windowFullscreen = fs ? 'true' : 'false';
        }
      } catch (err) {
        console.warn('Fullscreen check error:', err);
      }
    };

    const triggerCheck = () => {
      void checkFullscreen();
      setTimeout(checkFullscreen, 100);
      setTimeout(checkFullscreen, 250);
      setTimeout(checkFullscreen, 500);
      setTimeout(checkFullscreen, 800);
    };

    triggerCheck();

    const interval = setInterval(checkFullscreen, 350);

    let unlisten: (() => void) | undefined;
    void appWindow.onResized(() => {
      triggerCheck();
    }).then(listener => {
      unlisten = listener;
    });

    window.addEventListener('resize', triggerCheck);

    return () => {
      isCancelled = true;
      clearInterval(interval);
      unlisten?.();
      window.removeEventListener('resize', triggerCheck);
    };
  }, []);

  const [isLicenseActive, setIsLicenseActive] = useState(true);
  const [isLicenseHovered, setIsLicenseHovered] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const licenseHideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLicenseMouseEnter = () => {
    if (licenseHideTimer.current) clearTimeout(licenseHideTimer.current);
    setIsLicenseHovered(true);
  };

  const handleLicenseMouseLeave = () => {
    licenseHideTimer.current = setTimeout(() => setIsLicenseHovered(false), 400);
  };

  const licenseInfo = {
    type: 'Faculty Multi-Seat',
    licensee: 'Academic Licensee',
    key: 'CSPLS-8492-7104-FAC-2026',
    expiryDate: 'Dec 31, 2026',
    daysRemaining: 108,
  };

  const handleCopyKey = () => {
    navigator.clipboard.writeText(licenseInfo.key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  return (
    <header className="titlebar window-drag" id="titlebar">
      {/* ─── Left Section: Traffic Lights & Brand ─── */}
      <div className="titlebar__left no-drag">
        {!isFullscreen && (
          <div className="titlebar__traffic-light-space" aria-hidden="true" />
        )}
        <div 
          className="brand" 
          role="button" 
          tabIndex={0} 
          title="Go to Home"
          style={{ cursor: 'pointer' }}
          onClick={() => openTab({ type: 'get-started', title: 'Home' })}
        >
          <svg className="brand__logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="CSPLS Logo">
            <rect width="48" height="48" rx="10" fill="#6B4EE6" />
            <circle cx="16" cy="16" r="4" fill="#FFFFFF" />
            <circle cx="32" cy="18" r="4" fill="#C7D2FE" />
            <circle cx="20" cy="32" r="5" fill="#EEF2FF" />
            <circle cx="34" cy="32" r="3.5" fill="#A5B4FC" />
            <path d="M16 16L32 18M16 16L20 32M20 32L34 32M32 18L34 32" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.85" />
          </svg>
          <span className="brand__name">CSPLS</span>
        </div>
      </div>

      {/* ─── Center Section: Browser / VSCode Tabs ─── */}
      <div className="titlebar__center no-drag">
        <TabBar />
      </div>

      {/* ─── Right Section: Actions & User ─── */}
      <div className="titlebar__right no-drag">
        <button
          className="icon-btn"
          id="theme-toggle-btn"
          title={`Switch to ${theme === 'light' ? 'Dark' : 'Light'} Mode`}
          type="button"
          onClick={toggleTheme}
        >
          <span className="material-symbols-outlined">
            {theme === 'light' ? 'dark_mode' : 'light_mode'}
          </span>
        </button>
        <button className="icon-btn" title="Settings" type="button" onClick={() => setIsSettingsOpen(true)}>
          <span className="material-symbols-outlined">settings</span>
        </button>

        <span className="v-divider" />

        {/* ─── License Status Indicator (Green/Red) & Hover Details ─── */}
        <div 
          className="license-indicator-wrapper" 
          style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
          onMouseEnter={handleLicenseMouseEnter}
          onMouseLeave={handleLicenseMouseLeave}
        >
          <button
            type="button"
            className="license-status-btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '26px',
              height: '26px',
              borderRadius: '50%',
              border: `1.5px solid ${isLicenseActive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              backgroundColor: isLicenseActive ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              padding: 0,
            }}
            title={isLicenseActive ? 'License Active' : 'License Inactive'}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: isLicenseActive ? '#10B981' : '#EF4444',
                boxShadow: isLicenseActive ? '0 0 6px rgba(16, 185, 129, 0.6)' : '0 0 6px rgba(239, 68, 68, 0.6)',
              }}
            />
          </button>

          {isLicenseHovered && (
            <div className="license-popup-card">
              <div className="license-popup-card__header">
                <span className="license-popup-card__status-dot" style={{ backgroundColor: isLicenseActive ? '#10B981' : '#EF4444' }} />
                <span className="license-popup-card__status-text" style={{ color: isLicenseActive ? '#059669' : '#DC2626' }}>
                  {isLicenseActive ? 'Active' : 'Inactive'}
                </span>
                <span className="license-popup-card__type">{licenseInfo.type}</span>
              </div>

              <div className="license-popup-card__rows">
                <div className="license-popup-card__row">
                  <span className="license-popup-card__key-label">Licensee</span>
                  <span className="license-popup-card__key-value">{licenseInfo.licensee}</span>
                </div>
                <div className="license-popup-card__row">
                  <span className="license-popup-card__key-label">Expiry</span>
                  <span className="license-popup-card__key-value">
                    {isLicenseActive ? `${licenseInfo.daysRemaining} days (${licenseInfo.expiryDate})` : 'Inactive'}
                  </span>
                </div>
                <div className="license-popup-card__row license-popup-card__row--mono">
                  <span className="license-popup-card__key-label">Key</span>
                  <span className="license-popup-card__key-mono">{licenseInfo.key}</span>
                  <button
                    type="button"
                    className="license-popup-card__copy-btn"
                    onClick={handleCopyKey}
                    title={copiedKey ? 'Copied!' : 'Copy key'}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '13px' }}>
                      {copiedKey ? 'check' : 'content_copy'}
                    </span>
                  </button>
                </div>
              </div>

              <div className="license-popup-card__footer">
                <button
                  type="button"
                  className={`license-popup-card__action ${isLicenseActive ? 'license-popup-card__action--deactivate' : 'license-popup-card__action--activate'}`}
                  onClick={() => setIsLicenseActive(!isLicenseActive)}
                >
                  {isLicenseActive ? 'Deactivate' : 'Activate'}
                </button>
                <button
                  type="button"
                  className="license-popup-card__action license-popup-card__action--manage"
                  onClick={() => { setIsSettingsOpen(true); setIsLicenseHovered(false); }}
                >
                  Manage
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default TitleBar;
