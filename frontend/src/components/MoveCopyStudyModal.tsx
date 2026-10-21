import React, { useState, useEffect } from 'react';
import { useStore, type Study, type Workspace } from '../store';
import { api, type RecentWorkspace } from '../utils/api';

interface MoveCopyStudyModalProps {
  isOpen: boolean;
  onClose: () => void;
  mode: 'move' | 'copy';
  study: Study | null;
}

export const MoveCopyStudyModal: React.FC<MoveCopyStudyModalProps> = ({
  isOpen,
  onClose,
  mode,
  study,
}) => {
  const {
    workspaces,
    addWorkspace,
    moveStudyToWorkspace,
    copyStudyToWorkspace,
  } = useStore();

  const [selectedWsId, setSelectedWsId] = useState<string>('');
  const [newStudyName, setNewStudyName] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentWorkspaces, setRecentWorkspaces] = useState<RecentWorkspace[]>([]);

  // Find the source workspace
  const sourceWorkspace = workspaces.find((w) => w.id === study?.workspaceId);

  // Load recent workspaces on open
  useEffect(() => {
    if (isOpen) {
      api.getRecentWorkspaces().then((recents) => {
        if (Array.isArray(recents)) {
          setRecentWorkspaces(recents);
        }
      }).catch(console.warn);
    }
  }, [isOpen]);

  // Combine store workspaces and recent workspaces that aren't in store yet
  const allAvailableWorkspaces: Array<{ id: string; name: string; path?: string }> = React.useMemo(() => {
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

  // Candidate workspaces for target selection
  const targetCandidates = React.useMemo(() => {
    if (!study) return [];
    if (mode === 'move') {
      return allAvailableWorkspaces.filter((w) => w.id !== study.workspaceId && w.path !== sourceWorkspace?.path);
    }
    return allAvailableWorkspaces;
  }, [allAvailableWorkspaces, study, mode, sourceWorkspace]);

  // Reset state on open or study change
  useEffect(() => {
    if (isOpen && study) {
      setError(null);
      setIsSubmitting(false);

      // Default selected workspace
      const defaultTarget = targetCandidates[0];
      setSelectedWsId(defaultTarget ? defaultTarget.id : '');

      // Default study name for copy mode
      if (mode === 'copy') {
        const isSameWs = defaultTarget?.id === study.workspaceId;
        setNewStudyName(isSameWs ? `${study.name} (Copy)` : study.name);
      } else {
        setNewStudyName(study.name);
      }
    }
  }, [isOpen, study, mode, targetCandidates]);

  // When target workspace changes in copy mode, update suggested name
  const handleWorkspaceChange = (targetId: string) => {
    setSelectedWsId(targetId);
    if (mode === 'copy' && study) {
      const isSameWs = targetId === study.workspaceId;
      if (isSameWs && !newStudyName.includes('Copy')) {
        setNewStudyName(`${study.name} (Copy)`);
      }
    }
  };

  if (!isOpen || !study) return null;

  const targetWs = targetCandidates.find((w) => w.id === selectedWsId);

  const handleBrowseTargetWorkspace = async () => {
    setError(null);
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: 'Select Destination Workspace Folder',
      });
      if (!selected || typeof selected !== 'string') return;

      const wsRes = await api.openWorkspace(selected);
      if (wsRes.error || !wsRes.workspace) {
        setError(wsRes.error || 'Selected folder is not a valid workspace.');
        return;
      }

      const existingWs = workspaces.find(
        (w) => (w.path || '').toLowerCase() === selected.toLowerCase()
      );

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
        setError('Cannot move a study to the same workspace it currently belongs to.');
        return;
      }

      setSelectedWsId(targetId);
    } catch (err: any) {
      setError(err?.message || 'Failed to select workspace folder');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetWs || !targetWs.path) {
      setError('Please select a destination workspace.');
      return;
    }

    if (mode === 'move' && (targetWs.id === study.workspaceId || targetWs.path === sourceWorkspace?.path)) {
      setError('Cannot move study to the same workspace.');
      return;
    }

    const cleanName = newStudyName.trim();
    if (mode === 'copy' && !cleanName) {
      setError('Please enter a name for the copied study.');
      return;
    }

    // If targetWs is a recent workspace not yet in store, add it to store
    let actualWorkspaceId = targetWs.id;
    if (actualWorkspaceId.startsWith('recent_') && targetWs.path) {
      const existing = workspaces.find((w) => (w.path || '').toLowerCase() === targetWs.path?.toLowerCase());
      if (existing) {
        actualWorkspaceId = existing.id;
      } else {
        actualWorkspaceId = `ws_${Date.now()}`;
        addWorkspace({
          id: actualWorkspaceId,
          name: targetWs.name,
          path: targetWs.path,
          modifiedAt: new Date().toISOString(),
        });
      }
    }

    setError(null);
    setIsSubmitting(true);

    try {
      if (mode === 'move') {
        const res = await moveStudyToWorkspace(study.id, actualWorkspaceId, targetWs.path);
        if (!res.success) {
          setError(res.error || 'Failed to move study.');
          setIsSubmitting(false);
          return;
        }
      } else {
        const res = await copyStudyToWorkspace(study.id, actualWorkspaceId, targetWs.path, cleanName);
        if (!res.success) {
          setError(res.error || 'Failed to copy study.');
          setIsSubmitting(false);
          return;
        }
      }
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Operation failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay active" style={{ display: 'flex' }} onClick={onClose}>
      <div className="modal" style={{ maxWidth: '480px', width: '100%' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="material-symbols-outlined" style={{ fontSize: '20px', color: 'var(--color-primary)' }}>
              {mode === 'move' ? 'drive_file_move' : 'content_copy'}
            </span>
            <h2 className="modal__title">
              {mode === 'move' ? 'Move Study to Workspace' : 'Copy Study to Workspace'}
            </h2>
          </div>
          <button className="icon-btn icon-btn--sm" type="button" onClick={onClose} disabled={isSubmitting}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal__body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Source info */}
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 'var(--radius-md, 6px)',
                background: 'var(--color-bg-subtle, rgba(255,255,255,0.04))',
                border: '1px solid var(--color-border-subtle, rgba(255,255,255,0.08))',
                fontSize: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--color-text-secondary)' }}>
                <span className="material-symbols-outlined" style={{ fontSize: '15px' }}>folder</span>
                <span>Current Study:</span>
                <strong style={{ color: 'var(--color-text-primary)' }}>{study.name}</strong>
              </div>
              {sourceWorkspace && (
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', paddingLeft: '21px' }}>
                  Workspace: {sourceWorkspace.name}
                </div>
              )}
            </div>

            {/* Target workspace selector */}
            <div className="modal__field">
              <label className="modal__label" htmlFor="destination-workspace" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Destination Workspace</span>
                <button
                  type="button"
                  onClick={handleBrowseTargetWorkspace}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-primary, #3b82f6)',
                    cursor: 'pointer',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: 0,
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>folder_open</span>
                  <span>Browse Folder...</span>
                </button>
              </label>

              {targetCandidates.length > 0 ? (
                <select
                  id="destination-workspace"
                  className="modal__input"
                  value={selectedWsId}
                  onChange={(e) => handleWorkspaceChange(e.target.value)}
                  disabled={isSubmitting}
                >
                  {targetCandidates.map((ws) => (
                    <option key={ws.id} value={ws.id}>
                      {ws.name} {ws.path ? `(${ws.path})` : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', padding: '8px 0' }}>
                  No other workspace found. Click <strong>Browse Folder...</strong> to select a workspace folder on your computer.
                </div>
              )}
            </div>

            {/* Target Path Preview */}
            {targetWs?.path && (
              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', wordBreak: 'break-all' }}>
                <span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Destination Path: </span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{targetWs.path}</span>
              </div>
            )}

            {/* Study Name input for Copy mode */}
            {mode === 'copy' && (
              <div className="modal__field">
                <label className="modal__label" htmlFor="new-study-name">
                  New Study Name
                </label>
                <input
                  type="text"
                  id="new-study-name"
                  className="modal__input"
                  placeholder="e.g. Technology Acceptance Model (Copy)"
                  value={newStudyName}
                  onChange={(e) => setNewStudyName(e.target.value)}
                  disabled={isSubmitting}
                  autoFocus
                />
              </div>
            )}

            {/* Mode description info */}
            {mode === 'move' && (
              <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', lineHeight: '1.4' }}>
                This study and all its models and datasets will be moved from <strong>{sourceWorkspace?.name || 'current workspace'}</strong> into <strong>{targetWs?.name || 'the selected workspace'}</strong>.
              </div>
            )}

            {error && (
              <div
                style={{
                  color: 'var(--color-danger, #ef4444)',
                  fontSize: '12px',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm, 4px)',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                }}
              >
                {error}
              </div>
            )}
          </div>

          <div className="modal__footer">
            <button
              className="modal__btn-cancel"
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              className="modal__btn-create"
              type="submit"
              disabled={!targetWs || isSubmitting || (mode === 'copy' && !newStudyName.trim())}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
                {mode === 'move' ? 'drive_file_move' : 'content_copy'}
              </span>
              <span>{isSubmitting ? 'Processing...' : mode === 'move' ? 'Move Study' : 'Copy Study'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
export default MoveCopyStudyModal;
