import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import WorkspaceModal from '../components/WorkspaceModal';
import InputDialog from '../components/InputDialog';
import { api } from '../utils/api';

const GetStarted = () => {
  const navigate = useNavigate();
  const { workspaces, addWorkspace, removeWorkspace, setActiveWorkspace, archivedWorkspaces, trash, archiveWorkspace, renameWorkspace, trashWorkspace } = useStore();
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [inputDialogConfig, setInputDialogConfig] = useState<{isOpen: boolean; title: string; placeholder: string; submitLabel: string; onSubmit: (val: string) => void}>({
    isOpen: false, title: '', placeholder: '', submitLabel: '', onSubmit: () => {}
  });

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
        if (res.error) {
          alert(res.error);
          return;
        }
        const wsName = res.workspace?.name || selected.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() || 'Workspace';
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
        navigate('/workspace');
      }
    } catch (err) {
      console.warn('Tauri open dialog error:', err);
      const fallback = window.prompt('Enter workspace directory path:');
      if (fallback) {
        const res = await api.openWorkspace(fallback);
        if (res.error) {
          alert(res.error);
          return;
        }
        const wsName = res.workspace?.name || fallback.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() || 'Workspace';
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
        navigate('/workspace');
      }
    }
  };



  return (
    <>
      <header className="titlebar window-drag" id="titlebar">

    
    <div className="titlebar__left no-drag">
      
      <div className="titlebar__traffic-light-space" aria-hidden="true"></div>

      
      <div className="brand">
        <svg className="brand__logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="CSPLS Logo">
          <rect width="48" height="48" rx="10" fill="#6B4EE6"/>
          <circle cx="16" cy="16" r="4" fill="#FFFFFF"/>
          <circle cx="32" cy="18" r="4" fill="#C7D2FE"/>
          <circle cx="20" cy="32" r="5" fill="#EEF2FF"/>
          <circle cx="34" cy="32" r="3.5" fill="#A5B4FC"/>
          <path d="M16 16L32 18M16 16L20 32M20 32L34 32M32 18L34 32" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.85"/>
        </svg>
        <span className="brand__name">CSPLS</span>
      </div>
    </div>

    
    <div className="titlebar__center no-drag">
      <span className="titlebar__version">CSPLS 1.1</span>
    </div>

    
    <div className="titlebar__right no-drag">
      <button className="icon-btn" id="theme-toggle-btn" title="Toggle Theme" type="button">
        <span className="material-symbols-outlined">light_mode</span>
      </button>
      <button className="icon-btn" title="Settings" type="button">
        <span className="material-symbols-outlined">settings</span>
      </button>

      <span className="v-divider"></span>

      <div className="user-badge" role="button" tabIndex={0}>
        <div className="user-badge__avatar">
          <span>MV</span>
          <span className="user-badge__status"></span>
        </div>
        <span className="user-badge__name">M. Vance</span>
      </div>
    </div>
  </header>


  
  <div className="app-body">

    
    <aside className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`} id="sidebar">

      
      <div className="sidebar__top">
        <div>
          
          <div className="sidebar-header" style={{'paddingBottom': '10px', 'borderBottom': 'none'}}>
            <span className="sidebar-header__label">Workspaces</span>
            <div className="sidebar-header__actions">
              <button className="icon-btn icon-btn--sm" title="Search workspaces" type="button" onClick={() => setInputDialogConfig({isOpen: true, title: 'Search Workspaces', placeholder: 'Enter workspace name...', submitLabel: 'Search', onSubmit: () => {}})}>
                <span className="material-symbols-outlined">search</span>
              </button>
              <button className="icon-btn icon-btn--sm" title="Open Workspace Folder" type="button" onClick={handleOpenWorkspace}>
                <span className="material-symbols-outlined">folder_open</span>
              </button>
              <button className="sidebar-create-folder-btn" title="Create Workspace" type="button" onClick={() => setIsWorkspaceModalOpen(true)}>
                <svg fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
                  <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"></path>
                  <line x1="12" x2="12" y1="10" y2="16"></line>
                  <line x1="9" x2="15" y1="13" y2="13"></line>
                </svg>
              </button>
              <button className="icon-btn icon-btn--sm" id="sidebar-collapse-btn" title="Collapse sidebar" type="button" onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}>
                <span className="material-symbols-outlined">left_panel_close</span>
              </button>
            </div>
          </div>

          <div id="sidebar-ws-list" style={{'display': 'flex', 'flexDirection': 'column', 'gap': '2px'}}>
            {workspaces.map(ws => (
              <button 
                key={ws.id} 
                className="sidebar-item" 
                type="button" 
                onClick={async () => {
                  if (ws.path) {
                    await api.openWorkspace(ws.path);
                  }
                  setActiveWorkspace(ws.id);
                  navigate('/workspace');
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  useStore.getState().openContextMenu(e.clientX, e.clientY, [
                    {
                      id: 'remove-from-sidebar',
                      label: 'Remove from Sidebar',
                      icon: 'close',
                      action: () => {
                        removeWorkspace(ws.id);
                      }
                    },
                    {
                      id: 'delete-workspace',
                      label: 'Delete Workspace',
                      icon: 'delete',
                      danger: true,
                      action: async () => {
                        if (window.confirm(`Are you sure you want to permanently delete workspace "${ws.name}" and all its files? This cannot be undone.`)) {
                          if (ws.path) {
                            const res = await api.deleteWorkspace(ws.path);
                            if (res.error) {
                              alert('Failed to delete workspace files: ' + res.error);
                            }
                          }
                          removeWorkspace(ws.id);
                        }
                      }
                    }
                  ]);
                }}
              >
                <span className="sidebar-item__left">
                  <span className="material-symbols-outlined">folder</span>
                  <span>{ws.name}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      
      <div className="sidebar__bottom">
        <button className="sidebar-item" type="button" data-action="archive" onClick={() => navigate('/workspace?panel=archive')}>
          <span className="sidebar-item__left">
            <span className="material-symbols-outlined">inventory_2</span>
            <span>Archive</span>
          </span>
          <span className="sidebar-item__badge">{archivedWorkspaces.length}</span>
        </button>
        <button className="sidebar-item" type="button" onClick={() => navigate('/workspace?panel=trash')}>
          <span className="sidebar-item__left"><span className="material-symbols-outlined">delete</span><span>Trash</span></span>
          <span className="sidebar-item__badge">{trash.length}</span>
        </button>

        <button className="sidebar-item" type="button" data-action="docs">
          <span className="sidebar-item__left">
            <span className="material-symbols-outlined">menu_book</span>
            <span>Documentation</span>
          </span>
        </button>

        <button className="sidebar-item" type="button" data-action="samples">
          <span className="sidebar-item__left">
            <span className="material-symbols-outlined">science</span>
            <span>Sample Projects</span>
          </span>
        </button>

        <button className="sidebar-item" type="button" data-action="feedback">
          <span className="sidebar-item__left">
            <span className="material-symbols-outlined">feedback</span>
            <span className="truncate">Feedback &amp; Reports</span>
          </span>
        </button>

        
        <div className="license-badge">
          <span className="material-symbols-outlined license-badge__icon">verified_user</span>
          <div className="license-badge__content">
            <span className="license-badge__label">Faculty Multi-Seat</span>
            <span className="license-badge__status">
              <span className="license-badge__dot"></span>
              Active
            </span>
          </div>
        </div>
      </div>
    </aside>


    
    <main className="main-content">
      <div className="main-content__inner">

        
        <div className="page-header animate-fade-in">
          <div className="page-header__text">
            <h1 className="page-header__title">Get Started</h1>
            <p className="page-header__subtitle">Welcome to CSPLS. Set up your workspace or explore guided sample models to begin.</p>
          </div>
          <div className="page-header__actions" style={{ display: 'flex', gap: '8px' }}>
            <button className="btn btn-primary" type="button" onClick={handleOpenWorkspace}>
              <span className="material-symbols-outlined">folder_open</span>
              <span>Open Workspace</span>
            </button>
            <button className="btn btn-primary" type="button" onClick={() => setIsWorkspaceModalOpen(true)}>
              <span className="material-symbols-outlined">add</span>
              <span>Create Workspace</span>
              <kbd className="kbd">⌘W</kbd>
            </button>
          </div>

        </div>

        
        <div className="content-grid">

          
          <div style={{'display': 'flex', 'flexDirection': 'column', 'gap': '24px'}}>

            
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
                <button className="release-card__changelog" type="button">
                  Technical Changelog
                  <span className="material-symbols-outlined">arrow_forward</span>
                </button>
              </div>
            </div>

            
            <div className="animate-fade-in animate-fade-in-delay-2">
              <div className="section-header">
                <h2 className="section-header__title">Documentation &amp; Quick Guides</h2>
                <a href="#" className="section-header__link">Browse all docs</a>
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
                Sample Projects to Get Started
              </div>
            </div>

            <div className="project-list">

              
              <div onClick={() => navigate('/workspace')} className="project-card animate-fade-in animate-fade-in-delay-4" style={{ cursor: 'pointer' }}>
                <div className="project-card__content">
                  <div className="project-card__info">
                    <h3 className="project-card__title">Corporate Reputation Model</h3>
                    <p className="project-card__desc">Reflective-formative benchmark assessing competence and likeability on customer retention.</p>
                  </div>
                </div>
              </div>

              
              <div onClick={() => navigate('/workspace')} className="project-card animate-fade-in animate-fade-in-delay-5" style={{ cursor: 'pointer' }}>
                <div className="project-card__content">
                  <div className="project-card__info">
                    <h3 className="project-card__title">Customer Satisfaction Index (ACSI/ECSI)</h3>
                    <p className="project-card__desc">Classic standard with consistent PLSc correction for purely reflective latent construct paths.</p>
                  </div>
                </div>
              </div>

              
              <div onClick={() => navigate('/workspace')} className="project-card animate-fade-in animate-fade-in-delay-6" style={{ cursor: 'pointer' }}>
                <div className="project-card__content">
                  <div className="project-card__info">
                    <h3 className="project-card__title">Technology Acceptance Model (TAM 3)</h3>
                    <p className="project-card__desc">Moderated mediation investigating perceived usefulness and ease of use with interaction terms.</p>
                  </div>
                </div>
              </div>

              
              <div onClick={() => navigate('/workspace')} className="project-card animate-fade-in animate-fade-in-delay-7" style={{ cursor: 'pointer' }}>
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
