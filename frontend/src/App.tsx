import React, { useEffect } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { useStore } from './store';
import TitleBar from './components/TitleBar';
import ContextMenu from './components/ContextMenu';
import SettingsModal from './components/SettingsModal';
import ConfirmDeleteModal from './components/ConfirmDeleteModal';
import GetStarted from './pages/GetStarted';
import Dashboard from './pages/Dashboard';
import ModelEditor from './pages/ModelEditor';
import ArchiveView from './pages/ArchiveView';

function App() {
  const { tabs, activeTabId, settings, theme } = useStore();

  const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0];

  // Apply theme & font preference to document
  useEffect(() => {
    if (settings.theme === 'dark') {
      document.documentElement.dataset.theme = 'dark';
    } else {
      document.documentElement.dataset.theme = 'light';
    }
  }, [settings.theme]);

  useEffect(() => {
    const fontMap: Record<string, string> = {
      'Inter': "'Inter', sans-serif",
      'Roboto': "'Roboto', sans-serif",
      'JetBrains Mono': "'JetBrains Mono', monospace",
      'System': "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
    };
    if (settings.fontFamily && fontMap[settings.fontFamily]) {
      document.body.style.fontFamily = fontMap[settings.fontFamily];
    }
  }, [settings.fontFamily]);

  const renderContent = () => {
    if (!activeTab || activeTab.type === 'get-started') {
      return <GetStarted />;
    }
    if (activeTab.type === 'workspace') {
      return <Dashboard key={activeTab.id} />;
    }
    if (activeTab.type === 'model') {
      return <ModelEditor key={activeTab.id} />;
    }
    if (activeTab.type === 'archive') {
      return <ArchiveView key={activeTab.id} />;
    }
    return <GetStarted />;
  };

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
      <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <TitleBar />
        <ContextMenu />
        <SettingsModal />
        <ConfirmDeleteModal />
        <div style={{ flex: 1, minHeight: 0, position: 'relative', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {renderContent()}
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
