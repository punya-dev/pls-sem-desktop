import React, { useState } from 'react';
import { useStore, type Workspace } from '../store';
import WorkspaceModal from '../components/WorkspaceModal';

export const ArchiveView: React.FC = () => {
  const { 
    workspaces, 
    archivedWorkspaces, 
    restoreWorkspace, 
    setActiveWorkspace,
    studies,
    models,
    datasetsByStudy,
    openTab,
  } = useStore();

  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Set<string>>(new Set());
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isWorkspaceSearchOpen, setIsWorkspaceSearchOpen] = useState(false);
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);

  const toggleExpand = (id: string) => {
    setExpandedWorkspaces((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const filteredWorkspaces = workspaces.filter(workspace => 
    workspace.name.toLocaleLowerCase().includes(workspaceQuery.toLocaleLowerCase())
  );

  return (
    <>
      <div className="app-body">
        {/* Sidebar */}
        <aside className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`} id="sidebar">
          <div className="sidebar__top">
            <div className="sidebar-ws-container">
              <div className="sidebar-header" style={{ paddingBottom: '10px', borderBottom: 'none' }}>
                {isWorkspaceSearchOpen ? (
                  <div className="inline-search-wrap">
                    <input 
                      autoFocus 
                      className="sidebar-inline-search" 
                      value={workspaceQuery} 
                      onChange={e => setWorkspaceQuery(e.target.value)} 
                      onBlur={() => { if (!workspaceQuery) setIsWorkspaceSearchOpen(false); }} 
                      placeholder="Filter workspaces…" 
                    />
                    {workspaceQuery && (
                      <button className="inline-search-clear" type="button" aria-label="Clear workspace search" onMouseDown={e => e.preventDefault()} onClick={() => setWorkspaceQuery('')}>
                        ×
                      </button>
                    )}
                  </div>
                ) : (
                  <span className="sidebar-header__label">Workspaces</span>
                )}
                <div className="sidebar-header__actions">
                  <button 
                    className={`icon-btn icon-btn--sm ${isWorkspaceSearchOpen ? 'active' : ''}`} 
                    title="Filter workspaces" 
                    type="button" 
                    onClick={() => { setIsWorkspaceSearchOpen(open => !open); if (isWorkspaceSearchOpen) setWorkspaceQuery(''); }}
                  >
                    <span className="material-symbols-outlined">search</span>
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

              <div id="sidebar-ws-list" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {filteredWorkspaces.map(ws => (
                  <button 
                    key={ws.id} 
                    className="sidebar-item" 
                    type="button" 
                    onClick={() => {
                      setActiveWorkspace(ws.id);
                      openTab({ type: 'workspace', title: ws.name, workspaceId: ws.id });
                    }}
                  >
                    <span className="sidebar-item__left">
                      <span className="material-symbols-outlined">folder</span>
                      <span>{ws.name}</span>
                    </span>
                  </button>
                ))}
                {isWorkspaceSearchOpen && workspaceQuery && filteredWorkspaces.length === 0 && (
                  <span className="inline-search-empty">No workspaces found</span>
                )}
              </div>
            </div>
          </div>

          <div className="sidebar__bottom">
            <button className="sidebar-item active" type="button" data-action="archive">
              <span className="sidebar-item__left">
                <span className="material-symbols-outlined">inventory_2</span>
                <span>Archive</span>
              </span>
              <span className="sidebar-item__badge">{archivedWorkspaces.length}</span>
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
          </div>
        </aside>

        {/* Main Content: Exact previous design */}
        <main className="ws-main">
          <div className="ws-inner">
            <div className="ws-header animate-fade-in">
              <div className="ws-header__left">
                <h1 className="ws-header__greeting">Archived workspaces</h1>
              </div>
            </div>

            <div style={{ flex: '1', display: 'flex', flexDirection: 'column' }}>
              <div className="studies-header">
                <div className="studies-header__left" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Archived Workspaces</span>
                  <span className="sidebar-item__badge">{archivedWorkspaces.length}</span>
                </div>
              </div>

              <div className="studies-list">
                {archivedWorkspaces.length ? archivedWorkspaces.map(workspace => {
                  const isExpanded = expandedWorkspaces.has(workspace.id);
                  const archivedStudies = studies.filter(study => study.workspaceId === workspace.id);
                  return (
                    <div className="study-entry archive-entry" key={workspace.id}>
                      <div className="study-row" onClick={() => toggleExpand(workspace.id)}>
                        <div className="study-row__left">
                          <span className="material-symbols-outlined study-folder">inventory_2</span>
                          <span className="study-row__name">{workspace.name}</span>
                          <span className="study-row__count">Archived</span>
                        </div>
                        <div className="study-row__meta">
                          <button 
                            className="archive-restore-btn" 
                            type="button" 
                            onClick={event => { 
                              event.stopPropagation(); 
                              restoreWorkspace(workspace.id); 
                            }}
                          >
                            Restore
                          </button>
                          <span className="study-row__chevron">
                            <span 
                              className="material-symbols-outlined study-chevron" 
                              style={{ transform: isExpanded ? 'rotate(0deg)' : 'rotate(-90deg)' }}
                            >
                              {isExpanded ? 'expand_more' : 'chevron_right'}
                            </span>
                          </span>
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="study-children archive-children">
                          {archivedStudies.length ? archivedStudies.map(study => (
                            <div key={study.id}>
                              <div className="file-row archive-readonly">
                                <div className="file-row__left">
                                  <span className="material-symbols-outlined">folder</span>
                                  <span>{study.name}</span>
                                  <span className="file-badge file-badge--default">Study</span>
                                </div>
                                <div className="file-row__meta">
                                  <span className="file-row__time">{study.lastModified}</span>
                                </div>
                              </div>
                              {datasetsByStudy[study.id] && (
                                <div className="file-row archive-readonly archive-file">
                                  <div className="file-row__left">
                                    <span className="material-symbols-outlined">dataset</span>
                                    <span>{datasetsByStudy[study.id].filename}</span>
                                    <span className="file-badge file-badge--default">{datasetsByStudy[study.id].rows.length} rows</span>
                                  </div>
                                </div>
                              )}
                              {models.filter(model => model.studyId === study.id).map(model => (
                                <div className="file-row archive-readonly archive-file" key={model.id}>
                                  <div className="file-row__left">
                                    <span className="material-symbols-outlined">account_tree</span>
                                    <span>{model.name}</span>
                                    <span className="file-badge file-badge--default">{model.type}</span>
                                  </div>
                                  <div className="file-row__meta">
                                    <span className="file-row__time">{model.lastModified}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )) : (
                            <div className="archive-empty">No studies in this workspace.</div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                }) : (
                  <div className="empty-state" style={{ padding: '32px 16px', textAlign: 'center' }}>
                    No archived workspaces.
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>

      <WorkspaceModal isOpen={isWorkspaceModalOpen} onClose={() => setIsWorkspaceModalOpen(false)} />
    </>
  );
};

export default ArchiveView;
