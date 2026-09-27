import React, { useState } from 'react';
import { useStore } from '../store';
import { api } from '../utils/api';
import WorkspaceModal from './WorkspaceModal';

interface AppSidebarProps {
  activeNav?: 'workspace' | 'archive' | 'docs' | 'samples' | 'feedback' | 'changelog';
}

export const AppSidebar: React.FC<AppSidebarProps> = ({ activeNav }) => {
  const {
    workspaces,
    activeWorkspaceId,
    setActiveWorkspace,
    openTab,
    archiveWorkspace,
    deleteWorkspace,
    renameWorkspace,
    requestDelete,
    archivedWorkspaces,
    isSidebarCollapsed,
    toggleSidebar,
  } = useStore();

  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [isWorkspaceSearchOpen, setIsWorkspaceSearchOpen] = useState(false);
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const [editingWsId, setEditingWsId] = useState<string | null>(null);
  const [editWsName, setEditWsName] = useState('');

  const filteredWorkspaces = workspaces.filter((ws) =>
    ws.name.toLowerCase().includes(workspaceQuery.toLowerCase())
  );

  const commitWsRename = (wsId: string) => {
    if (editWsName.trim()) {
      renameWorkspace(wsId, editWsName.trim());
    }
    setEditingWsId(null);
  };

  return (
    <>
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
                    onChange={(e) => setWorkspaceQuery(e.target.value)}
                    onBlur={() => {
                      if (!workspaceQuery) setIsWorkspaceSearchOpen(false);
                    }}
                    placeholder="Filter…"
                  />
                  {workspaceQuery && (
                    <button
                      className="inline-search-clear"
                      type="button"
                      aria-label="Clear workspace search"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => setWorkspaceQuery('')}
                    >
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
                  title="Search workspaces"
                  type="button"
                  onClick={() => {
                    if (isSidebarCollapsed) {
                      // Expand sidebar first, then open search
                      toggleSidebar();
                      setTimeout(() => setIsWorkspaceSearchOpen(true), 150);
                    } else {
                      setIsWorkspaceSearchOpen((open) => !open);
                      if (isWorkspaceSearchOpen) setWorkspaceQuery('');
                    }
                  }}
                >
                  <span className="material-symbols-outlined">search</span>
                </button>
                <button
                  className="sidebar-create-folder-btn"
                  title="Create Workspace"
                  type="button"
                  onClick={() => setIsWorkspaceModalOpen(true)}
                >
                  <svg
                    fill="none"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"></path>
                    <line x1="12" x2="12" y1="10" y2="16"></line>
                    <line x1="9" x2="15" y1="13" y2="13"></line>
                  </svg>
                </button>
                <button
                  className="icon-btn icon-btn--sm"
                  id="sidebar-collapse-btn"
                  title={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                  type="button"
                  onClick={toggleSidebar}
                >
                  <span className="material-symbols-outlined">left_panel_close</span>
                </button>
              </div>
            </div>

            <div id="sidebar-ws-list" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {filteredWorkspaces.map((ws) => (
                <div
                  key={ws.id}
                  className={`sidebar-item ${ws.id === activeWorkspaceId && activeNav === 'workspace' ? 'active' : ''}`}
                  onClick={async () => {
                    if (editingWsId !== ws.id) {
                      if (ws.path) {
                        try {
                          await api.openWorkspace(ws.path);
                        } catch (err) {
                          console.warn('Failed opening workspace path:', err);
                        }
                      }
                      setActiveWorkspace(ws.id);
                      openTab({ type: 'workspace', title: ws.name, workspaceId: ws.id });
                    }
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    useStore.getState().openContextMenu(e.clientX, e.clientY, [
                      {
                        id: 'rename',
                        label: 'Rename Workspace',
                        icon: 'edit',
                        action: () => {
                          setEditingWsId(ws.id);
                          setEditWsName(ws.name);
                        },
                      },
                      {
                        id: 'duplicate',
                        label: 'Duplicate Workspace',
                        icon: 'content_copy',
                        action: () =>
                          useStore.getState().addWorkspace({
                            ...ws,
                            id: `ws_${Date.now()}`,
                            name: `${ws.name} copy`,
                          }),
                      },
                      {
                        id: 'archive',
                        label: 'Archive Workspace',
                        icon: 'inventory_2',
                        action: () => archiveWorkspace(ws.id),
                      },
                      {
                        id: 'delete',
                        label: 'Delete Workspace',
                        icon: 'delete',
                        danger: true,
                        action: () => {
                          requestDelete({
                            title: 'Delete Workspace',
                            itemName: ws.name,
                            message:
                              'Are you sure? This workspace and all its contents will be permanently deleted and cannot be recovered.',
                            onConfirm: async () => {
                              if (ws.path) {
                                try {
                                  await api.deleteWorkspace(ws.path);
                                } catch (err) {
                                  console.warn('Failed deleting workspace files:', err);
                                }
                              }
                              deleteWorkspace(ws.id);
                            },
                          });
                        },
                      },
                    ]);
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <span className="sidebar-item__left" style={{ width: '100%', overflow: 'hidden' }}>
                    <span className="material-symbols-outlined">folder</span>
                    {editingWsId === ws.id ? (
                      <input
                        autoFocus
                        type="text"
                        className="inline-seamless-rename-input"
                        value={editWsName}
                        size={Math.max(editWsName.length, 1)}
                        onChange={(e) => setEditWsName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitWsRename(ws.id);
                          else if (e.key === 'Escape') setEditingWsId(null);
                        }}
                        onBlur={() => commitWsRename(ws.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <span>{ws.name}</span>
                    )}
                  </span>
                </div>
              ))}
              {isWorkspaceSearchOpen && workspaceQuery && filteredWorkspaces.length === 0 && (
                <span className="inline-search-empty">No workspaces found</span>
              )}
            </div>
          </div>
        </div>

        <div className="sidebar__bottom">
          <button
            className={`sidebar-item ${activeNav === 'archive' ? 'active' : ''}`}
            type="button"
            data-action="archive"
            onClick={() => openTab({ id: 'tab-archive', type: 'archive', title: 'Archive' })}
          >
            <span className="sidebar-item__left">
              <span className="material-symbols-outlined">inventory_2</span>
              <span>Archive</span>
            </span>
            {archivedWorkspaces.length > 0 && (
              <span className="sidebar-item__badge">{archivedWorkspaces.length}</span>
            )}
          </button>

          <button
            className={`sidebar-item ${activeNav === 'docs' ? 'active' : ''}`}
            type="button"
            data-action="docs"
            onClick={() => openTab({ id: 'tab-docs', type: 'docs', title: 'Documentation' })}
          >
            <span className="sidebar-item__left">
              <span className="material-symbols-outlined">menu_book</span>
              <span>Documentation</span>
            </span>
          </button>

          <button
            className={`sidebar-item ${activeNav === 'samples' ? 'active' : ''}`}
            type="button"
            data-action="samples"
            onClick={() => openTab({ id: 'tab-samples', type: 'samples', title: 'Sample Projects' })}
          >
            <span className="sidebar-item__left">
              <span className="material-symbols-outlined">science</span>
              <span>Sample Projects</span>
            </span>
          </button>

          <button
            className={`sidebar-item ${activeNav === 'feedback' ? 'active' : ''}`}
            type="button"
            data-action="feedback"
            onClick={() => openTab({ id: 'tab-feedback', type: 'feedback', title: 'Feedback & Reports' })}
          >
            <span className="sidebar-item__left">
              <span className="material-symbols-outlined">feedback</span>
              <span className="truncate">Feedback &amp; Reports</span>
            </span>
          </button>
        </div>
      </aside>

      <WorkspaceModal
        isOpen={isWorkspaceModalOpen}
        onClose={() => setIsWorkspaceModalOpen(false)}
      />
    </>
  );
};

export default AppSidebar;
