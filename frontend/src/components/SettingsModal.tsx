import React, { useState, useEffect } from 'react';
import { useStore, LICENSE_INFO, type AppSettings } from '../store';
import { ACCENT_PRESETS, getContrastTextColor, applyAccentColor } from '../utils/theme';

type SettingsTab = 'about' | 'appearance' | 'calculation' | 'canvas';

export const SettingsModal: React.FC = () => {
  const { 
    isSettingsOpen, 
    setIsSettingsOpen, 
    settings, 
    updateSettings, 
    settingsActiveTab, 
    setSettingsActiveTab, 
    isLicenseActive, 
    setIsLicenseActive,
    setSidebarCollapsed
  } = useStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>(settingsActiveTab || 'about');
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'checking' | 'latest'>('idle');
  const [copiedLicenseKey, setCopiedLicenseKey] = useState(false);

  const currentAccent = settings.accentColor || '#6B4EE6';
  const [hexInput, setHexInput] = useState(currentAccent);

  useEffect(() => {
    if (settingsActiveTab) {
      setActiveTab(settingsActiveTab);
    }
  }, [settingsActiveTab, isSettingsOpen]);

  useEffect(() => {
    setHexInput(settings.accentColor || '#6B4EE6');
  }, [settings.accentColor]);

  const handleAccentSelect = (colorHex: string) => {
    updateSettings({ accentColor: colorHex });
    const isDark = document.documentElement.dataset.theme === 'dark';
    applyAccentColor(colorHex, isDark);
    setHexInput(colorHex);
  };

  const handleHexChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setHexInput(val);
    if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
      handleAccentSelect(val);
    }
  };

  const isCustomSelected = !ACCENT_PRESETS.some(
    (p) => p.color.toLowerCase() === currentAccent.toLowerCase()
  );

  if (!isSettingsOpen) return null;

  const handleClose = () => setIsSettingsOpen(false);

  const handleTabChange = (tabId: SettingsTab) => {
    setActiveTab(tabId);
    setSettingsActiveTab(tabId);
  };

  const handleCheckUpdates = () => {
    setUpdateStatus('checking');
    setTimeout(() => {
      setUpdateStatus('latest');
      setTimeout(() => setUpdateStatus('idle'), 4000);
    }, 1200);
  };

  const handleCopyLicenseKey = () => {
    navigator.clipboard.writeText(LICENSE_INFO.key);
    setCopiedLicenseKey(true);
    setTimeout(() => setCopiedLicenseKey(false), 2000);
  };

  const tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'about', label: 'General', icon: 'info' },
    { id: 'appearance', label: 'Appearance', icon: 'palette' },
    { id: 'calculation', label: 'Calculation', icon: 'calculate' },
    { id: 'canvas', label: 'Canvas', icon: 'tune' },
  ];

  return (
    <div className="modal-overlay active" style={{ display: 'flex', zIndex: 9999 }} onClick={handleClose}>
      <div className="settings-dialog" onClick={(e) => e.stopPropagation()}>

        {/* Sidebar */}
        <nav className="settings-sidebar">
          <div className="settings-sidebar__brand">Settings</div>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`settings-sidebar__item ${activeTab === tab.id ? 'settings-sidebar__item--active' : ''}`}
              onClick={() => handleTabChange(tab.id)}
            >
              <span className="material-symbols-outlined settings-sidebar__icon">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="settings-content">

          {/* ─── GENERAL & ABOUT ─── */}
          {activeTab === 'about' && (
            <>
              <div className="settings-section">
                <div className="settings-section__header">Application</div>
                <div className="settings-row settings-row--app">
                  <div className="settings-app-icon">ST</div>
                  <div className="settings-app-info">
                    <div className="settings-app-name">
                      StatSEM Desktop
                      <span className="settings-app-version">v{settings.version}</span>
                    </div>
                    <div className="settings-app-desc">Partial Least Squares Structural Equation Modeling</div>
                  </div>
                  <button
                    type="button"
                    className="settings-update-btn"
                    onClick={handleCheckUpdates}
                    disabled={updateStatus === 'checking'}
                  >
                    <span className={`material-symbols-outlined ${updateStatus === 'checking' ? 'settings-spin' : ''}`} style={{ fontSize: '14px' }}>
                      {updateStatus === 'checking' ? 'sync' : updateStatus === 'latest' ? 'check_circle' : 'update'}
                    </span>
                    {updateStatus === 'checking' ? 'Checking…' : updateStatus === 'latest' ? 'Up to date' : 'Check for Updates'}
                  </button>
                </div>
                {updateStatus === 'latest' && (
                  <div className="settings-update-ok">✓ You are on the latest version.</div>
                )}
              </div>

              {/* ─── LICENSE DETAILS ─── */}
              <div className="settings-section" id="settings-license-section">
                <div className="settings-section__header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span>License Details</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span 
                      style={{ 
                        width: '7px', 
                        height: '7px', 
                        borderRadius: '50%', 
                        backgroundColor: isLicenseActive ? '#10B981' : '#EF4444',
                        boxShadow: isLicenseActive ? '0 0 6px rgba(16, 185, 129, 0.6)' : '0 0 6px rgba(239, 68, 68, 0.6)',
                        display: 'inline-block' 
                      }} 
                    />
                    <span style={{ fontSize: '11px', fontWeight: 600, color: isLicenseActive ? '#059669' : '#DC2626' }}>
                      {isLicenseActive ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                </div>

                <div className="settings-row">
                  <div className="settings-row__label">License Type</div>
                  <span className="settings-badge" style={{ fontWeight: 600 }}>
                    {LICENSE_INFO.type}
                  </span>
                </div>

                <div className="settings-row">
                  <div className="settings-row__label">Licensee</div>
                  <div style={{ fontSize: '12.5px', fontWeight: 500, color: 'var(--color-text-primary)' }}>
                    {LICENSE_INFO.licensee}
                  </div>
                </div>

                <div className="settings-row">
                  <div className="settings-row__label">Expiry Date</div>
                  <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-text-primary)' }}>
                    {isLicenseActive ? `${LICENSE_INFO.daysRemaining} days remaining (${LICENSE_INFO.expiryDate})` : 'Inactive'}
                  </div>
                </div>

                <div className="settings-row">
                  <div className="settings-row__label">License Key</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <code style={{ 
                      fontSize: '11.5px', 
                      fontFamily: 'var(--font-mono)', 
                      backgroundColor: 'var(--color-bg-subtle, rgba(0,0,0,0.04))',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      border: '1px solid var(--color-border-subtle)',
                      color: 'var(--color-text-secondary)',
                      letterSpacing: '0.02em'
                    }}>
                      {LICENSE_INFO.key}
                    </code>
                    <button
                      type="button"
                      className="settings-icon-btn"
                      onClick={handleCopyLicenseKey}
                      title={copiedLicenseKey ? 'Copied!' : 'Copy key'}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '4px',
                        borderRadius: '4px',
                        color: copiedLicenseKey ? 'var(--color-accent)' : 'var(--color-text-muted)',
                        transition: 'color var(--transition-fast)'
                      }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
                        {copiedLicenseKey ? 'check' : 'content_copy'}
                      </span>
                    </button>
                  </div>
                </div>

                <div className="settings-row" style={{ borderBottom: 'none' }}>
                  <div>
                    <div className="settings-row__label">Manage Seat</div>
                    <div className="settings-row__desc">
                      {isLicenseActive 
                        ? 'Deactivating releases this seat to use on another machine.' 
                        : 'Activate to restore full academic multi-seat features.'}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={`settings-license-toggle-btn ${isLicenseActive ? 'settings-license-toggle-btn--deactivate' : 'settings-license-toggle-btn--activate'}`}
                    onClick={() => setIsLicenseActive(!isLicenseActive)}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
                      {isLicenseActive ? 'power_settings_new' : 'check_circle'}
                    </span>
                    {isLicenseActive ? 'Deactivate License' : 'Activate License'}
                  </button>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section__header">Links</div>
                <div className="settings-row">
                  <div className="settings-row__label">Official Website</div>
                  <a href={settings.websiteUrl} target="_blank" rel="noreferrer" className="settings-link">
                    statsem.org
                    <span className="material-symbols-outlined" style={{ fontSize: '12px' }}>open_in_new</span>
                  </a>
                </div>
              </div>
            </>
          )}

          {/* ─── APPEARANCE ─── */}
          {activeTab === 'appearance' && (
            <>
              <div className="settings-section">
                <div className="settings-section__header">Theme</div>
                <div className="settings-theme-grid">
                  {[
                    { id: 'light', label: 'Light', icon: 'light_mode' },
                    { id: 'dark', label: 'Dark', icon: 'dark_mode' },
                    { id: 'system', label: 'System', icon: 'settings_brightness' },
                  ].map((mode) => (
                    <button
                      key={mode.id}
                      type="button"
                      className={`settings-theme-btn ${settings.theme === mode.id ? 'settings-theme-btn--active' : ''}`}
                      onClick={() => {
                        updateSettings({ theme: mode.id as AppSettings['theme'] });
                        const isDark = mode.id === 'dark' || (mode.id === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
                        document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
                        if (isDark) {
                          document.documentElement.dataset.darkVariant = settings.darkVariant || 'default';
                        } else {
                          delete document.documentElement.dataset.darkVariant;
                        }
                      }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>{mode.icon}</span>
                      <span>{mode.label}</span>
                    </button>
                  ))}
                </div>

                {/* Dark variant — only shown when dark/system theme is active */}
                {(settings.theme === 'dark' || settings.theme === 'system') && (
                  <div style={{ marginTop: '12px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                      Dark Style
                    </div>
                    <div className="settings-theme-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                      {[
                        { id: 'default', label: 'Default', icon: 'dark_mode' },
                        { id: 'grayscale', label: 'Grayscale', icon: 'invert_colors_off' },
                        { id: 'true-black', label: 'True Black', icon: 'contrast' },
                      ].map((variant) => (
                        <button
                          key={variant.id}
                          type="button"
                          className={`settings-theme-btn ${(settings.darkVariant || 'default') === variant.id ? 'settings-theme-btn--active' : ''}`}
                          onClick={() => {
                            updateSettings({ darkVariant: variant.id as AppSettings['darkVariant'] });
                            if (document.documentElement.dataset.theme === 'dark') {
                              document.documentElement.dataset.darkVariant = variant.id;
                            }
                          }}
                        >
                          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>{variant.icon}</span>
                          <span style={{ fontSize: '11px' }}>{variant.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="settings-section">
                <div className="settings-section__header">Accent Color</div>
                <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '8px' }}>
                  Choose a signature pastel accent or pick any custom hue
                </div>

                <div className="settings-accent-grid">
                  {ACCENT_PRESETS.map((preset) => {
                    const isSelected = (settings.accentColor || '#6B4EE6').toLowerCase() === preset.color.toLowerCase();
                    const checkColor = getContrastTextColor(preset.color);
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        className={`settings-accent-btn ${isSelected ? 'settings-accent-btn--active' : ''}`}
                        onClick={() => handleAccentSelect(preset.color)}
                        title={`${preset.name}${preset.isDefault ? ' (Default)' : ''}`}
                      >
                        <div
                          className="settings-accent-swatch"
                          style={{ backgroundColor: preset.color }}
                        >
                          {isSelected && (
                            <span
                              className="material-symbols-outlined"
                              style={{ fontSize: '16px', color: checkColor, fontWeight: 700 }}
                            >
                              check
                            </span>
                          )}
                        </div>
                        <span className="settings-accent-label">
                          {preset.name}
                        </span>
                      </button>
                    );
                  })}

                  {/* Custom Color Option with native picker */}
                  <div
                    className={`settings-accent-btn settings-accent-custom-wrapper ${isCustomSelected ? 'settings-accent-btn--active' : ''}`}
                    title="Choose any custom hue"
                  >
                    <div
                      className="settings-accent-swatch"
                      style={
                        isCustomSelected
                          ? { backgroundColor: currentAccent }
                          : {
                              background:
                                'conic-gradient(from 180deg at 50% 50%, #EF4444 0deg, #F59E0B 60deg, #10B981 120deg, #06B6D4 180deg, #3B82F6 240deg, #8B5CF6 300deg, #EF4444 360deg)',
                            }
                      }
                    >
                      {isCustomSelected ? (
                        <span
                          className="material-symbols-outlined"
                          style={{
                            fontSize: '16px',
                            color: getContrastTextColor(currentAccent),
                            fontWeight: 700,
                          }}
                        >
                          check
                        </span>
                      ) : (
                        <span
                          className="material-symbols-outlined"
                          style={{ fontSize: '15px', color: '#FFFFFF', textShadow: '0 1px 2px rgba(0,0,0,0.6)' }}
                        >
                          palette
                        </span>
                      )}
                    </div>
                    <span className="settings-accent-label">Custom</span>
                    <input
                      type="color"
                      className="settings-accent-color-native-input"
                      value={currentAccent}
                      onChange={(e) => handleAccentSelect(e.target.value)}
                      title="Click to open color picker"
                    />
                  </div>
                </div>

                {/* Custom Hex input & Reset to Default */}
                <div className="settings-accent-custom-meta">
                  <div className="settings-accent-hex-group">
                    <span className="settings-accent-hex-label">Hex Code:</span>
                    <input
                      type="text"
                      className="settings-accent-hex-input"
                      value={hexInput}
                      placeholder="#6B4EE6"
                      maxLength={7}
                      onChange={handleHexChange}
                    />
                  </div>
                  {currentAccent.toLowerCase() !== '#6b4ee6' && (
                    <button
                      type="button"
                      className="settings-link"
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: '11px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                      }}
                      onClick={() => handleAccentSelect('#6B4EE6')}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '13px' }}>
                        restart_alt
                      </span>
                      Reset to Default
                    </button>
                  )}
                </div>

                {/* Live Accent Preview Box */}
                <div className="settings-accent-preview">
                  <span className="settings-accent-preview__label">Preview:</span>
                  <button type="button" className="settings-accent-preview__btn">
                    Primary Button
                  </button>
                  <span className="settings-accent-preview__pill">
                    <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
                      verified
                    </span>
                    Active Pill
                  </span>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-accent)' }}>
                    Active Accent Link
                  </span>
                </div>
              </div>

              {/* ─── SIDEBAR & NAVIGATION ─── */}
              <div className="settings-section">
                <div className="settings-section__header">Sidebar &amp; Navigation</div>
                <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '12px' }}>
                  Customize the positioning and behavior of the main navigation sidebar
                </div>

                <div className="settings-row" style={{ alignItems: 'flex-start', marginBottom: '16px' }}>
                  <div className="settings-row__label">
                    Sidebar Position
                    <div className="settings-row__desc">Position the sidebar on the left or right side of the screen</div>
                  </div>
                  <div className="settings-theme-grid" style={{ gridTemplateColumns: 'repeat(2, 100px)', gap: '8px' }}>
                    {[
                      { id: 'left', label: 'Left', icon: 'dock_to_left' },
                      { id: 'right', label: 'Right', icon: 'dock_to_right' },
                    ].map((pos) => {
                      const isActive = (settings.sidebarPosition || 'left') === pos.id;
                      return (
                        <button
                          key={pos.id}
                          type="button"
                          className={`settings-theme-btn ${isActive ? 'settings-theme-btn--active' : ''}`}
                          onClick={() => {
                            updateSettings({ sidebarPosition: pos.id as AppSettings['sidebarPosition'] });
                            document.documentElement.dataset.sidebarPosition = pos.id;
                          }}
                        >
                          <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                            {pos.icon}
                          </span>
                          <span>{pos.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="settings-row">
                  <div className="settings-row__label">
                    Lock Expanded Sidebar
                    <div className="settings-row__desc">Keep the sidebar permanently open and prevent automatic collapsing</div>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={Boolean(settings.lockExpandedSidebar)}
                    className={`settings-toggle ${settings.lockExpandedSidebar ? 'settings-toggle--on' : ''}`}
                    onClick={() => {
                      const nextLocked = !settings.lockExpandedSidebar;
                      updateSettings({ lockExpandedSidebar: nextLocked });
                      if (nextLocked) {
                        setSidebarCollapsed(false);
                      }
                    }}
                  >
                    <span className="settings-toggle__thumb" />
                  </button>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section__header">Typography</div>
                <div className="settings-row">
                  <div className="settings-row__label">
                    Font Family
                    <div className="settings-row__desc">Typeface applied across canvas and tables</div>
                  </div>
                  <select
                    id="settings-font"
                    className="settings-select"
                    value={settings.fontFamily}
                    onChange={(e) => {
                      const font = e.target.value as AppSettings['fontFamily'];
                      updateSettings({ fontFamily: font });
                      const fontMap: Record<string, string> = {
                        'Inter': "'Inter', sans-serif",
                        'Roboto': "'Roboto', sans-serif",
                        'JetBrains Mono': "'JetBrains Mono', monospace",
                        'System': 'system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
                      };
                      document.body.style.fontFamily = fontMap[font] || font;
                    }}
                  >
                    <option value="Inter">Inter (Default)</option>
                    <option value="Roboto">Roboto</option>
                    <option value="JetBrains Mono">JetBrains Mono</option>
                    <option value="System">System Default</option>
                  </select>
                </div>
                <div className="settings-row">
                  <div className="settings-row__label">
                    Language
                    <div className="settings-row__desc">Locale formatting and UI language</div>
                  </div>
                  <select
                    id="settings-language"
                    className="settings-select"
                    value={settings.language}
                    onChange={(e) => updateSettings({ language: e.target.value as AppSettings['language'] })}
                  >
                    <option value="en">English (US)</option>
                    <option value="es">Español</option>
                    <option value="de">Deutsch</option>
                    <option value="fr">Français</option>
                    <option value="zh">中文</option>
                  </select>
                </div>
              </div>
            </>
          )}

          {/* ─── CALCULATION ─── */}
          {activeTab === 'calculation' && (
            <>
              <div className="settings-section">
                <div className="settings-section__header">Number Format</div>
                <div className="settings-theme-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                  {[
                    { id: 'point', label: 'Period  ( . )', preview: '1,000.25' },
                    { id: 'comma', label: 'Comma  ( , )', preview: '1.000,25' },
                  ].map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`settings-theme-btn ${settings.decimalSystem === item.id ? 'settings-theme-btn--active' : ''}`}
                      onClick={() => updateSettings({ decimalSystem: item.id as AppSettings['decimalSystem'] })}
                    >
                      <span style={{ fontSize: '13px', fontWeight: 600 }}>{item.label}</span>
                      <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', opacity: 0.55 }}>{item.preview}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section__header">Precision</div>
                <div className="settings-row">
                  <div className="settings-row__label">
                    Digits After Decimal
                    <div className="settings-row__desc">Shown in calculation tables and output panels</div>
                  </div>
                  <select
                    id="settings-precision"
                    className="settings-select"
                    value={settings.decimalDigits}
                    onChange={(e) => updateSettings({ decimalDigits: Number(e.target.value) })}
                  >
                    <option value={2}>2 — e.g. 0.35</option>
                    <option value={3}>3 — e.g. 0.347</option>
                    <option value={4}>4 — e.g. 0.3472</option>
                    <option value={5}>5 — e.g. 0.34721</option>
                    <option value={6}>6 — e.g. 0.347210</option>
                  </select>
                </div>
                <div className="settings-row">
                  <div className="settings-row__label">
                    Parallel Processors
                    <div className="settings-row__desc">CPU threads for bootstrapping computations</div>
                  </div>
                  <select
                    id="settings-processors"
                    className="settings-select"
                    value={String(settings.parallelProcessors)}
                    onChange={(e) => {
                      const val = e.target.value === 'all' ? 'all' : Number(e.target.value);
                      updateSettings({ parallelProcessors: val });
                    }}
                  >
                    <option value="all">All Cores (Recommended)</option>
                    <option value="8">8 Threads</option>
                    <option value="4">4 Threads</option>
                    <option value="2">2 Threads</option>
                    <option value="1">1 Thread</option>
                  </select>
                </div>
              </div>
            </>
          )}

          {/* ─── CANVAS & CONTROLS ─── */}
          {activeTab === 'canvas' && (
            <>
              <div className="settings-section">
                <div className="settings-section__header">Controls</div>
                <div className="settings-row">
                  <div className="settings-row__label">
                    Keyboard Layout
                    <div className="settings-row__desc">Configures canvas hotkeys and shortcuts</div>
                  </div>
                  <select
                    id="settings-keyboard"
                    className="settings-select"
                    value={settings.keyboardLayout}
                    onChange={(e) => updateSettings({ keyboardLayout: e.target.value as AppSettings['keyboardLayout'] })}
                  >
                    <option value="qwerty">QWERTY (Standard)</option>
                    <option value="azerty">AZERTY</option>
                    <option value="qwertz">QWERTZ</option>
                  </select>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section__header">Layout</div>
                <div className="settings-row">
                  <div className="settings-row__label">
                    Flip Orientation
                    <div className="settings-row__desc">Invert horizontal flow direction for new models</div>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={settings.flipOrientation}
                    className={`settings-toggle ${settings.flipOrientation ? 'settings-toggle--on' : ''}`}
                    onClick={() => updateSettings({ flipOrientation: !settings.flipOrientation })}
                  >
                    <span className="settings-toggle__thumb" />
                  </button>
                </div>
              </div>
            </>
          )}

          {/* Footer */}
          <div className="settings-footer">
            <span className="settings-footer__saved">Preferences saved automatically</span>
            <button type="button" className="settings-footer__done" onClick={handleClose}>Done</button>
          </div>
        </div>

      </div>
    </div>
  );
};

export default SettingsModal;
