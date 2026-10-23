import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import WorkspaceModal from '../components/WorkspaceModal';
import AppSidebar from '../components/AppSidebar';
import InputDialog from '../components/InputDialog';
import { api } from '../utils/api';
import { promptOpenWorkspaceFolder } from '../utils/workspace-import';

const GetStarted = () => {
  const navigate = useNavigate();
  const { workspaces, activeWorkspaceId, addWorkspace, setActiveWorkspace, openTab } = useStore();
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [isImportMenuOpen, setIsImportMenuOpen] = useState(false);
  const [inputDialogConfig, setInputDialogConfig] = useState<{isOpen: boolean; title: string; placeholder: string; submitLabel: string; initialValue?: string; onSubmit: (val: string) => void}>({
    isOpen: false, title: '', placeholder: '', submitLabel: '', onSubmit: () => {}
  });
  const importDropdownRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!isImportMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (importDropdownRef.current && !importDropdownRef.current.contains(e.target as Node)) {
        setIsImportMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isImportMenuOpen]);

  const rename = (title: string, initialValue: string, onSubmit: (name: string) => void) => {
    setInputDialogConfig({
      isOpen: true,
      title,
      placeholder: 'Enter new name...',
      submitLabel: 'Save',
      initialValue,
      onSubmit: (newName) => {
        if (newName.trim()) onSubmit(newName.trim());
      }
    });
  };

  const handleOpenSampleStudy = () => {
    const ws = workspaces.find(w => w.id === activeWorkspaceId) || workspaces[0];
    if (ws) {
      setActiveWorkspace(ws.id);
      openTab({ type: 'workspace', title: ws.name, workspaceId: ws.id });
    } else {
      setIsWorkspaceModalOpen(true);
    }
  };

  const handleOpenWorkspace = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: 'Open Workspace Folder'
      });
      if (selected && typeof selected === 'string') {
        const res = await api.openWorkspace(selected);
        if (res?.error) {
          alert(res.error);
          return;
        }
        const wsName = res?.workspace?.name || selected.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() || 'Workspace';
        const existing = workspaces.find(w => w.path === selected);
        const wsId = existing ? existing.id : selected;
        if (!existing) {
          addWorkspace({
            id: wsId,
            name: wsName,
            path: selected
          });
        }
        setActiveWorkspace(wsId);
        openTab({ type: 'workspace', title: wsName, workspaceId: wsId });
      }
    } catch (err) {
      console.warn('Tauri open dialog error:', err);
      const fallback = window.prompt('Enter workspace directory path:');
      if (fallback) {
        const res = await api.openWorkspace(fallback);
        if (res?.error) {
          alert(res.error);
          return;
        }
        const wsName = res?.workspace?.name || fallback.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() || 'Workspace';
        const existing = workspaces.find(w => w.path === fallback);
        const wsId = existing ? existing.id : fallback;
        if (!existing) {
          addWorkspace({
            id: wsId,
            name: wsName,
            path: fallback
          });
        }
        setActiveWorkspace(wsId);
        openTab({ type: 'workspace', title: wsName, workspaceId: wsId });
      }
    }
  };

  return (
    <>
      <div className="app-body">
        <AppSidebar />

        <main className="main-content">
          <div className="main-content__inner">

            <div className="page-header animate-fade-in">
              <div className="page-header__text">
                <h1 className="page-header__title">Get Started</h1>
                <p className="page-header__subtitle">Welcome to StatSEM. Set up your workspace or explore guided sample models to begin.</p>
              </div>
              <div className="page-header__actions">
                <div style={{ position: 'relative' }} ref={importDropdownRef}>
                  <button
                    className="btn btn-secondary"
                    type="button"
                    onClick={() => setIsImportMenuOpen((prev) => !prev)}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <span className="material-symbols-outlined">folder_open</span>
                    <span>Import / Open</span>
                    <span className="material-symbols-outlined" style={{ fontSize: '18px', marginLeft: '-2px' }}>
                      {isImportMenuOpen ? 'arrow_drop_up' : 'arrow_drop_down'}
                    </span>
                    <kbd className="kbd">⌘O</kbd>
                  </button>

                  {isImportMenuOpen && (
                    <div
                      className="no-drag animate-fade-in"
                      style={{
                        position: 'absolute',
                        top: 'calc(100% + 6px)',
                        left: 0,
                        minWidth: '230px',
                        background: 'var(--color-bg-surface)',
                        border: '1px solid var(--color-border-subtle)',
                        borderRadius: 'var(--radius-md)',
                        boxShadow: 'var(--shadow-lg)',
                        padding: '6px',
                        zIndex: 1000,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setIsImportMenuOpen(false);
                          promptOpenWorkspaceFolder('folder');
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          padding: '8px 10px',
                          borderRadius: 'var(--radius-sm)',
                          border: 'none',
                          background: 'transparent',
                          color: 'var(--color-text-primary)',
                          fontSize: '13px',
                          cursor: 'pointer',
                          textAlign: 'left',
                          width: '100%',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-base)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '18px', color: 'var(--color-accent)' }}>
                          folder_open
                        </span>
                        <div>
                          <div style={{ fontWeight: 500, fontSize: '12px' }}>Open Workspace Folder</div>
                          <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>StatSEM or SmartPLS folder</div>
                        </div>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setIsImportMenuOpen(false);
                          promptOpenWorkspaceFolder('zip');
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          padding: '8px 10px',
                          borderRadius: 'var(--radius-sm)',
                          border: 'none',
                          background: 'transparent',
                          color: 'var(--color-text-primary)',
                          fontSize: '13px',
                          cursor: 'pointer',
                          textAlign: 'left',
                          width: '100%',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-base)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '18px', color: 'var(--color-accent)' }}>
                          archive
                        </span>
                        <div>
                          <div style={{ fontWeight: 500, fontSize: '12px' }}>Import Archive (.zip)</div>
                          <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Workspace or Study archive</div>
                        </div>
                      </button>
                    </div>
                  )}
                </div>
                <button className="btn btn-primary" type="button" onClick={() => setIsWorkspaceModalOpen(true)}>
                  <span className="material-symbols-outlined">add</span>
                  <span>Create Workspace</span>
                  <kbd className="kbd">⌘W</kbd>
                </button>
              </div>
            </div>

            <div className="content-grid">

              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', minWidth: 0, width: '100%' }}>

                <div className="release-card animate-fade-in animate-fade-in-delay-1">
                  <div className="release-card__header">
                    <div className="release-card__header-left">
                      <h2 className="release-card__title">Release Notes</h2>
                    </div>
                    <span className="release-card__version">v1.1.0</span>
                  </div>

                  <div className="release-card__items">
                    <div className="release-item">
                      <div>
                        <span className="release-item__title">HTMT2 Discriminant Validity:</span>
                        Inference criteria implementing Henseler et al. (2023) unbiased geometric mean ratios.
                      </div>
                    </div>
                    <div className="release-item">
                      <div>
                        <span className="release-item__title">AVX-512 Matrix Subsystem:</span>
                        Vectorized LAPACK dense solver delivering 4.8x acceleration in inverse covariance decomposition.
                      </div>
                    </div>
                    <div className="release-item">
                      <div>
                        <span className="release-item__title">Consistent PLSc:</span>
                        Asymptotic normality correction for composite structures with parallel multi-core resampling.
                      </div>
                    </div>
                  </div>

                  <div className="release-card__footer">
                    <span className="release-card__date">November 18, 2024</span>
                    <button className="release-card__changelog" type="button" onClick={() => openTab({ type: 'changelog', title: 'Changelog' })}>
                      Technical Changelog
                      <span className="material-symbols-outlined">arrow_forward</span>
                    </button>
                  </div>
                </div>

                <div className="animate-fade-in animate-fade-in-delay-2">
                  <div className="section-header">
                    <h2 className="section-header__title">Documentation &amp; Quick Guides</h2>
                    <a href="#" className="section-header__link" onClick={(e) => { e.preventDefault(); openTab({ type: 'docs', title: 'Documentation' }); }}>Browse all docs</a>
                  </div>

                  <div className="doc-list">
                    <div className="doc-card">
                      <div className="doc-card__header">
                        <span className="doc-card__title">
                          Quick Start: Building Your First Path Model
                        </span>
                      </div>
                      <p className="doc-card__desc">Step-by-step walkthrough from variable import to bootstrapping structural paths.</p>
                    </div>

                    <div className="doc-card">
                      <div className="doc-card__header">
                        <span className="doc-card__title">
                          Data Format Guidelines (CSV, UTF-8)
                        </span>
                      </div>
                      <p className="doc-card__desc">Preparing indicator matrices, handling missing values, and delimiter configuration.</p>
                    </div>

                    <div className="doc-card">
                      <div className="doc-card__header">
                        <span className="doc-card__title">
                          SEMinR &amp; R-Bridge Setup
                        </span>
                      </div>
                      <p className="doc-card__desc">Exporting syntax scripts directly into R and synchronizing bidirectional workspaces.</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="animate-fade-in animate-fade-in-delay-3">
                <div className="section-header">
                  <div className="section-header__title">
                    Sample Studies to Get Started
                  </div>
                  <a href="#" className="section-header__link" onClick={(e) => { e.preventDefault(); openTab({ type: 'samples', title: 'Sample Studies' }); }}>More</a>
                </div>

                <div className="project-list">

                  <div onClick={handleOpenSampleStudy} className="project-card animate-fade-in animate-fade-in-delay-4" style={{ cursor: 'pointer' }}>
                    <div className="project-card__content">
                      <div className="project-card__info">
                        <h3 className="project-card__title">Corporate Reputation Model</h3>
                        <p className="project-card__desc">Reflective-formative benchmark assessing competence and likeability on customer retention.</p>
                      </div>
                    </div>
                  </div>

                  <div onClick={handleOpenSampleStudy} className="project-card animate-fade-in animate-fade-in-delay-5" style={{ cursor: 'pointer' }}>
                    <div className="project-card__content">
                      <div className="project-card__info">
                        <h3 className="project-card__title">Customer Satisfaction Index (ACSI/ECSI)</h3>
                        <p className="project-card__desc">Classic standard with consistent PLSc correction for purely reflective latent construct paths.</p>
                      </div>
                    </div>
                  </div>

                  <div onClick={handleOpenSampleStudy} className="project-card animate-fade-in animate-fade-in-delay-6" style={{ cursor: 'pointer' }}>
                    <div className="project-card__content">
                      <div className="project-card__info">
                        <h3 className="project-card__title">Technology Acceptance Model (TAM 3)</h3>
                        <p className="project-card__desc">Moderated mediation investigating perceived usefulness and ease of use with interaction terms.</p>
                      </div>
                    </div>
                  </div>

                  <div onClick={handleOpenSampleStudy} className="project-card animate-fade-in animate-fade-in-delay-7" style={{ cursor: 'pointer' }}>
                    <div className="project-card__content">
                      <div className="project-card__info">
                        <h3 className="project-card__title">Meta-Analysis &amp; Moderation</h3>
                        <p className="project-card__desc">Two-stage PLS-SEM tutorial template with random-effects weighting and latent moderation analysis.</p>
                      </div>
                    </div>
                  </div>

                </div>
              </div>

            </div>
          </div>
        </main>

      </div>

      <WorkspaceModal isOpen={isWorkspaceModalOpen} onClose={() => setIsWorkspaceModalOpen(false)} />
      <InputDialog 
        isOpen={inputDialogConfig.isOpen} 
        onClose={() => setInputDialogConfig(prev => ({...prev, isOpen: false}))}
        title={inputDialogConfig.title}
        placeholder={inputDialogConfig.placeholder}
        submitLabel={inputDialogConfig.submitLabel}
        onSubmit={inputDialogConfig.onSubmit}
      />
    </>
  );
};

export default GetStarted;
