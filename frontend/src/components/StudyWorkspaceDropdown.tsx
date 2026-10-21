import React, { useEffect, useRef, useState, useMemo } from 'react';
import { useStore, type Study, type Workspace } from '../store';
import { api, type RecentWorkspace } from '../utils/api';

interface StudyWorkspaceDropdownProps {
  isOpen: boolean;
  onClose: () => void;
  mode: 'move' | 'copy';
  study: Study | null;
  position: { x: number; y: number } | null;
}

export const StudyWorkspaceDropdown: React.FC<StudyWorkspaceDropdownProps> = ({
  isOpen,
  onClose,
  mode,
  study,
  position,
}) => {
  const {
    workspaces,
    addWorkspace,
    moveStudyToWorkspace,
    copyStudyToWorkspace,
  } = useStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [recentWorkspaces, setRecentWorkspaces] = useState<RecentWorkspace[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Fetch recent workspaces on open
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      api.getRecentWorkspaces().then((recents) => {
        if (Array.isArray(recents)) {
          setRecentWorkspaces(recents);
        }
      }).catch(console.warn);

      const timer = setTimeout(() => {
        searchInputRef.current?.focus();
      }, 40);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Click outside and escape key handling
  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('mousedown', handleOutsideClick);
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('mousedown', handleOutsideClick);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Combine store workspaces and recent workspaces
  const allWorkspaces: Array<{ id: string; name: string; path?: string }> = useMemo(() => {
    const list: Array<{ id: string; name: string; path?: string }> = [...workspaces];
    const existingPaths = new Set(workspaces.map((w) => (w.path || '').toLowerCase()));

    for (const recent of recentWorkspaces) {
      if (recent.path && !existingPaths.has(recent.path.toLowerCase())) {
        list.push({
          id: `recent_${recent.path}`,
          name: recent.name || recent.path.split(/[/\\]/).pop() || 'Workspace',
          path: recent.path,
        });
      }
    }
    return list;
  }, [workspaces, recentWorkspaces]);

  // Filter workspaces based on search query and mode
  const filteredWorkspaces = useMemo(() => {
    if (!study) return [];
    let list = allWorkspaces;

    if (mode === 'move') {
      const sourceWs = workspaces.find((w) => w.id === study.workspaceId);
      list = list.filter((w) => w.id !== study.workspaceId && w.path !== sourceWs?.path);
    }

    const query = searchQuery.toLowerCase().trim();
    if (!query) return list;

    return list.filter((w) =>
      w.name.toLowerCase().includes(query) || (w.path && w.path.toLowerCase().includes(query))
    );
  }, [allWorkspaces, study, mode, searchQuery, workspaces]);

  if (!isOpen || !study || !position) return null;

  // Calculate position constrained within viewport
  const DROPDOWN_WIDTH = 270;
  const DROPDOWN_HEIGHT = 320;
  let left = Math.min(position.x, window.innerWidth - DROPDOWN_WIDTH - 12);
  let top = Math.min(position.y, window.innerHeight - DROPDOWN_HEIGHT - 12);
  if (left < 10) left = 10;
  if (top < 10) top = 10;

  const handleSelectWorkspace = async (targetWs: { id: string; name: string; path?: string }) => {
    if (!targetWs.path) return;

    let targetWorkspaceId = targetWs.id;
    if (targetWorkspaceId.startsWith('recent_')) {
      const existing = workspaces.find((w) => (w.path || '').toLowerCase() === targetWs.path?.toLowerCase());
      if (existing) {
        targetWorkspaceId = existing.id;
      } else {
        targetWorkspaceId = `ws_${Date.now()}`;
        addWorkspace({
          id: targetWorkspaceId,
          name: targetWs.name,
          path: targetWs.path,
          modifiedAt: new Date().toISOString(),
        });
      }
    }

    if (mode === 'move') {
      await moveStudyToWorkspace(study.id, targetWorkspaceId, targetWs.path);
    } else {
      const isSameWs = targetWorkspaceId === study.workspaceId;
      const targetName = isSameWs ? `${study.name} copy` : study.name;
      await copyStudyToWorkspace(study.id, targetWorkspaceId, targetWs.path, targetName);
    }
    onClose();
  };

  const handleBrowseFolder = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: mode === 'move' ? 'Select Workspace Folder to Move Study into' : 'Select Workspace Folder to Copy Study into',
      });
      if (!selected || typeof selected !== 'string') return;

      const wsRes = await api.openWorkspace(selected);
      if (wsRes.error || !wsRes.workspace) {
        console.warn('Selected folder is not a valid workspace:', wsRes.error);
        return;
      }

      const existingWs = workspaces.find((w) => (w.path || '').toLowerCase() === selected.toLowerCase());
      let targetId: string;
      if (existingWs) {
        targetId = existingWs.id;
      } else {
        targetId = `ws_${Date.now()}`;
        addWorkspace({
          id: targetId,
          name: wsRes.workspace.name || selected.split(/[/\\]/).pop() || 'Workspace',
          path: selected,
          modifiedAt: new Date().toISOString(),
        });
      }

      if (mode === 'move' && targetId === study.workspaceId) {
        console.warn('Cannot move to the current workspace');
        return;
      }

      if (mode === 'move') {
        await moveStudyToWorkspace(study.id, targetId, selected);
      } else {
        const isSameWs = targetId === study.workspaceId;
        const targetName = isSameWs ? `${study.name} copy` : study.name;
        await copyStudyToWorkspace(study.id, targetId, selected, targetName);
      }
      onClose();
    } catch (err) {
      console.warn('Browse workspace folder error:', err);
    }
  };

  return (
    <div
      ref={dropdownRef}
      className="tab-menu-dropdown"
      style={{
        position: 'fixed',
        left: `${left}px`,
        top: `${top}px`,
        zIndex: 10000,
        width: `${DROPDOWN_WIDTH}px`,
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.18), 0 2px 6px rgba(0,0,0,0.08)',
      }}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div
        className="tab-menu-dropdown__header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingBottom: '4px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="material-symbols-outlined" style={{ fontSize: '15px', color: 'var(--color-primary)' }}>
            {mode === 'move' ? 'drive_file_move' : 'file_copy'}
          </span>
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-primary)', textTransform: 'none' }}>
            {mode === 'move' ? 'Move Study to…' : 'Duplicate Study to…'}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="tab-menu-dropdown__search-clear"
          title="Close"
        >
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>

      <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', padding: '0 6px 6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        Study: <span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>{study.name}</span>
      </div>

      {/* Search Input */}
      <div className="tab-menu-dropdown__search-wrap">
        <span className="material-symbols-outlined tab-menu-dropdown__search-icon">search</span>
        <input
          ref={searchInputRef}
          type="text"
          className="tab-menu-dropdown__search-input"
          placeholder="Search workspaces..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button
            type="button"
            className="tab-menu-dropdown__search-clear"
            onClick={() => {
              setSearchQuery('');
              searchInputRef.current?.focus();
            }}
            title="Clear search"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        )}
      </div>

      {/* Workspaces List */}
      <div className="tab-menu-dropdown__list custom-scroll" style={{ maxHeight: '200px' }}>
        {filteredWorkspaces.length === 0 ? (
          <div className="tab-menu-dropdown__empty">
            {mode === 'move' && allWorkspaces.length <= 1
              ? 'No other workspaces found'
              : `No workspaces matching "${searchQuery}"`}
          </div>
        ) : (
          filteredWorkspaces.map((ws) => (
            <button
              key={ws.id}
              type="button"
              className="tab-menu-dropdown__item"
              onClick={() => handleSelectWorkspace(ws)}
              title={ws.path || ws.name}
            >
              <span className="material-symbols-outlined">folder</span>
              <span className="tab-menu-dropdown__item-title">{ws.name}</span>
              {ws.id === study.workspaceId && (
                <span className="tab-menu-dropdown__badge">Current</span>
              )}
            </button>
          ))
        )}
      </div>

      <div className="tab-menu-dropdown__divider" />

      {/* Footer / Browse folder */}
      <div className="tab-menu-dropdown__footer">
        <button
          type="button"
          className="tab-menu-dropdown__item"
          onClick={handleBrowseFolder}
        >
          <span className="material-symbols-outlined">folder_open</span>
          <span className="tab-menu-dropdown__item-title">Browse folder...</span>
        </button>
      </div>
    </div>
  );
};

export default StudyWorkspaceDropdown;
