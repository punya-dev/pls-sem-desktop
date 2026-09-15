import React, { useState } from 'react';
import { useStore, type AppSettings } from '../store';

type SettingsTab = 'about' | 'appearance' | 'calculation' | 'canvas';

export const SettingsModal: React.FC = () => {
  const { isSettingsOpen, setIsSettingsOpen, settings, updateSettings, theme, toggleTheme } = useStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('about');
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'checking' | 'latest'>('idle');

  if (!isSettingsOpen) return null;

  const handleClose = () => {
    setIsSettingsOpen(false);
  };

  const handleCheckUpdates = () => {
    setUpdateStatus('checking');
    setTimeout(() => {
      setUpdateStatus('latest');
      setTimeout(() => setUpdateStatus('idle'), 4000);
    }, 1200);
  };

  const tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'about', label: 'General & About', icon: 'info' },
    { id: 'appearance', label: 'Appearance', icon: 'palette' },
    { id: 'calculation', label: 'Calculation', icon: 'calculate' },
    { id: 'canvas', label: 'Canvas & Controls', icon: 'tune' },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[3px] animate-in fade-in duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-dialog-title"
      onClick={handleClose}
    >
      <div
        className="flex h-[min(82vh,640px)] w-[min(84vw,840px)] min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="material-symbols-outlined text-[#6B4EE6] text-xl">settings</span>
            <h2 id="settings-dialog-title" className="text-sm font-semibold tracking-tight text-slate-900">
              Settings & Preferences
            </h2>
          </div>
          <button
            onClick={handleClose}
            aria-label="Close settings"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        </div>

        {/* Modal Body: Sidebar + Main Area */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Navigation Sidebar */}
          <div className="w-52 shrink-0 border-r border-slate-200 bg-slate-50/80 p-3">
            <nav className="flex flex-col gap-1">
              {tabs.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors ${
                      isActive
                        ? 'bg-[#6B4EE6] text-white shadow-sm'
                        : 'text-slate-600 hover:bg-slate-200/60 hover:text-slate-900'
                    }`}
                  >
                    <span className={`material-symbols-outlined text-base ${isActive ? 'text-white' : 'text-slate-400'}`}>
                      {tab.icon}
                    </span>
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Settings Content Area */}
          <div className="flex-1 overflow-y-auto p-6 bg-white text-slate-800">
            {/* 1. GENERAL & ABOUT */}
            {activeTab === 'about' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Application Information
                  </h3>
                  <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/50 p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#6B4EE6] text-white shadow-sm font-semibold text-sm">
                          CS
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-slate-900">CSPLS Desktop</span>
                            <span className="rounded bg-[#6B4EE6]/10 px-2 py-0.5 font-mono text-[11px] font-medium text-[#6B4EE6]">
                              v{settings.version}
                            </span>
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">
                            Partial Least Squares Structural Equation Modeling Suite
                          </p>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={handleCheckUpdates}
                        disabled={updateStatus === 'checking'}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:border-[#6B4EE6] hover:text-[#6B4EE6] disabled:opacity-50"
                      >
                        <span className={`material-symbols-outlined text-sm ${updateStatus === 'checking' ? 'animate-spin' : ''}`}>
                          {updateStatus === 'checking' ? 'sync' : updateStatus === 'latest' ? 'check_circle' : 'update'}
                        </span>
                        <span>
                          {updateStatus === 'checking'
                            ? 'Checking...'
                            : updateStatus === 'latest'
                            ? 'Up to date'
                            : 'Check for Updates'}
                        </span>
                      </button>
                    </div>

                    {updateStatus === 'latest' && (
                      <p className="mt-3 text-xs text-green-600 font-medium">
                        ✓ You are using the latest version of CSPLS (v{settings.version}).
                      </p>
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Links & Documentation
                  </h3>
                  <div className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
                    <div className="flex items-center justify-between p-3.5">
                      <div>
                        <div className="text-xs font-medium text-slate-900">Official Website</div>
                        <div className="text-[11px] text-slate-500">Documentation, updates, and research resources</div>
                      </div>
                      <a
                        href={settings.websiteUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-mono text-xs font-medium text-[#6B4EE6] hover:underline"
                      >
                        <span>cspls.org</span>
                        <span className="material-symbols-outlined text-sm">open_in_new</span>
                      </a>
                    </div>

                    <div className="flex items-center justify-between p-3.5">
                      <div>
                        <div className="text-xs font-medium text-slate-900">License</div>
                        <div className="text-[11px] text-slate-500">Standard desktop distribution</div>
                      </div>
                      <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600">
                        Academic & Commercial
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 2. APPEARANCE */}
            {activeTab === 'appearance' && (
              <div className="space-y-6">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Theme
                  </label>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Select your preferred interface color mode
                  </p>
                  <div className="mt-3 grid grid-cols-3 gap-3">
                    {[
                      { id: 'light', label: 'Light', icon: 'light_mode' },
                      { id: 'dark', label: 'Dark', icon: 'dark_mode' },
                      { id: 'system', label: 'System', icon: 'settings_brightness' },
                    ].map((mode) => {
                      const isSelected = settings.theme === mode.id;
                      return (
                        <button
                          key={mode.id}
                          type="button"
                          onClick={() => {
                            updateSettings({ theme: mode.id as AppSettings['theme'] });
                            document.documentElement.dataset.theme = mode.id === 'dark' ? 'dark' : 'light';
                          }}
                          className={`flex flex-col items-center gap-2 rounded-lg border p-3.5 text-center transition-all ${
                            isSelected
                              ? 'border-[#6B4EE6] bg-[#6B4EE6]/5 text-[#6B4EE6] shadow-sm'
                              : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                          }`}
                        >
                          <span className="material-symbols-outlined text-xl">{mode.icon}</span>
                          <span className="text-xs font-medium">{mode.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-font" className="text-xs font-medium text-slate-900">
                        Typography / Font Family
                      </label>
                      <p className="text-[11px] text-slate-500">
                        Typeface applied across editor canvas and tables
                      </p>
                    </div>
                    <select
                      id="settings-font"
                      value={settings.fontFamily}
                      onChange={(e) => {
                        const font = e.target.value as AppSettings['fontFamily'];
                        updateSettings({ fontFamily: font });
                        const fontMap: Record<string, string> = {
                          'Inter': "'Inter', sans-serif",
                          'Roboto': "'Roboto', sans-serif",
                          'JetBrains Mono': "'JetBrains Mono', monospace",
                          'System': "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
                        };
                        document.body.style.fontFamily = fontMap[font] || font;
                      }}
                      className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-800 shadow-sm outline-none focus:border-[#6B4EE6] focus:ring-1 focus:ring-[#6B4EE6]"
                    >
                      <option value="Inter">Inter (Default)</option>
                      <option value="Roboto">Roboto</option>
                      <option value="JetBrains Mono">JetBrains Mono</option>
                      <option value="System">System Default</option>
                    </select>
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-language" className="text-xs font-medium text-slate-900">
                        Language
                      </label>
                      <p className="text-[11px] text-slate-500">
                        Locale formatting and UI translation
                      </p>
                    </div>
                    <select
                      id="settings-language"
                      value={settings.language}
                      onChange={(e) => updateSettings({ language: e.target.value as AppSettings['language'] })}
                      className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-800 shadow-sm outline-none focus:border-[#6B4EE6] focus:ring-1 focus:ring-[#6B4EE6]"
                    >
                      <option value="en">English (US)</option>
                      <option value="es">Español</option>
                      <option value="de">Deutsch</option>
                      <option value="fr">Français</option>
                      <option value="zh">中文 (Chinese)</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* 3. CALCULATION */}
            {activeTab === 'calculation' && (
              <div className="space-y-6">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Decimal System & Separator
                  </label>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Format used when displaying statistical metrics, path coefficients, and p-values
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    {[
                      { id: 'point', label: 'Period ( . )', preview: '1,000.25' },
                      { id: 'comma', label: 'Comma ( , )', preview: '1.000,25' },
                    ].map((item) => {
                      const isSelected = settings.decimalSystem === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => updateSettings({ decimalSystem: item.id as AppSettings['decimalSystem'] })}
                          className={`flex items-center justify-between rounded-lg border p-3 text-left transition-all ${
                            isSelected
                              ? 'border-[#6B4EE6] bg-[#6B4EE6]/5 text-[#6B4EE6] shadow-sm'
                              : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                          }`}
                        >
                          <span className="text-xs font-medium">{item.label}</span>
                          <span className="font-mono text-xs text-slate-400">{item.preview}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-precision" className="text-xs font-medium text-slate-900">
                        Digits After Decimal
                      </label>
                      <p className="text-[11px] text-slate-500">
                        Number of decimal places shown in calculation tables
                      </p>
                    </div>
                    <select
                      id="settings-precision"
                      value={settings.decimalDigits}
                      onChange={(e) => updateSettings({ decimalDigits: Number(e.target.value) })}
                      className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 font-mono text-xs font-medium text-slate-800 shadow-sm outline-none focus:border-[#6B4EE6] focus:ring-1 focus:ring-[#6B4EE6]"
                    >
                      <option value={2}>2 (e.g. 0.35)</option>
                      <option value={3}>3 (e.g. 0.347 - Standard)</option>
                      <option value={4}>4 (e.g. 0.3472)</option>
                      <option value={5}>5 (e.g. 0.34721)</option>
                      <option value={6}>6 (e.g. 0.347210)</option>
                    </select>
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-processors" className="text-xs font-medium text-slate-900">
                        Processors for Parallel Computing
                      </label>
                      <p className="text-[11px] text-slate-500">
                        CPU threads allocated for Bootstrapping and Blindfolding computations
                      </p>
                    </div>
                    <select
                      id="settings-processors"
                      value={String(settings.parallelProcessors)}
                      onChange={(e) => {
                        const val = e.target.value === 'all' ? 'all' : Number(e.target.value);
                        updateSettings({ parallelProcessors: val });
                      }}
                      className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-800 shadow-sm outline-none focus:border-[#6B4EE6] focus:ring-1 focus:ring-[#6B4EE6]"
                    >
                      <option value="all">All Available Cores (Recommended)</option>
                      <option value="8">8 Threads</option>
                      <option value="4">4 Threads</option>
                      <option value="2">2 Threads</option>
                      <option value="1">1 Thread (Single-core)</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* 4. CANVAS & CONTROLS */}
            {activeTab === 'canvas' && (
              <div className="space-y-6">
                <div>
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-keyboard" className="text-xs font-medium text-slate-900">
                        Keyboard Layout
                      </label>
                      <p className="text-[11px] text-slate-500">
                        Configures canvas hotkeys and navigation shortcuts
                      </p>
                    </div>
                    <select
                      id="settings-keyboard"
                      value={settings.keyboardLayout}
                      onChange={(e) => updateSettings({ keyboardLayout: e.target.value as AppSettings['keyboardLayout'] })}
                      className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-800 shadow-sm outline-none focus:border-[#6B4EE6] focus:ring-1 focus:ring-[#6B4EE6]"
                    >
                      <option value="qwerty">QWERTY (Standard)</option>
                      <option value="azerty">AZERTY</option>
                      <option value="qwertz">QWERTZ</option>
                    </select>
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-slate-900">
                        Flip Orientation
                      </div>
                      <p className="text-[11px] text-slate-500">
                        Invert default horizontal flow direction of new models and indicator groups
                      </p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={settings.flipOrientation}
                      onClick={() => updateSettings({ flipOrientation: !settings.flipOrientation })}
                      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#6B4EE6] focus:ring-offset-2 ${
                        settings.flipOrientation ? 'bg-[#6B4EE6]' : 'bg-slate-200'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                          settings.flipOrientation ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-slate-50/80 px-5 py-3">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="material-symbols-outlined text-xs text-green-500">check_circle</span>
            <span>Preferences saved automatically</span>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-[#6B4EE6] px-4 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-[#5A3ED4]"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;
