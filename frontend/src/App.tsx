import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getCurrentWindow } from '@tauri-apps/api/window';
import GetStarted from './pages/GetStarted';
import Dashboard from './pages/Dashboard';
import ModelEditor from './pages/ModelEditor';
import ContextMenu from './components/ContextMenu';

function App() {
  useEffect(() => {
    // Native macOS controls are intentionally hidden by the OS in fullscreen.
    // Remove their reservation so the app header stays visually balanced.
    if (!('__TAURI_INTERNALS__' in window)) return;

    const appWindow = getCurrentWindow();
    const syncFullscreenState = async () => {
      document.body.dataset.windowFullscreen = String(await appWindow.isFullscreen());
    };
    let unlisten: (() => void) | undefined;

    void syncFullscreenState();
    void appWindow.onResized(() => void syncFullscreenState()).then(listener => {
      unlisten = listener;
    });

    return () => unlisten?.();
  }, []);

  useEffect(() => {
    // Prevent Backspace key from triggering browser back navigation outside editable inputs
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Backspace') {
        const target = e.target as HTMLElement | null;
        const isEditable = !!(target && (
          target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable ||
          target.getAttribute('contenteditable') === 'true'
        ));
        if (!isEditable) {
          e.preventDefault();
        }
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  return (
    <BrowserRouter>
      <ContextMenu />
      <Routes>
        <Route path="/" element={<GetStarted />} />
        <Route path="/workspace" element={<Dashboard />} />
        <Route path="/model/:id" element={<ModelEditor />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
