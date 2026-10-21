import React, { useState, useEffect } from 'react';
import { useStore } from '../store';
import { api } from '../utils/api';
import { processData } from '../utils/dataset-parser';

interface StudyModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
}

const StudyModal = ({ isOpen, onClose, workspaceId }: StudyModalProps) => {
  const [name, setName] = useState('');
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(workspaceId);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isImportMenuOpen, setIsImportMenuOpen] = useState(false);

  const { workspaces, activeWorkspaceId, addStudy, setActiveStudy } = useStore();
  const currentWorkspaceId = selectedWorkspaceId || workspaceId || activeWorkspaceId;
  const currentWorkspace = workspaces.find(w => w.id === currentWorkspaceId);

  useEffect(() => {
    if (isOpen) {
      setName('');
      setSelectedWorkspaceId(workspaceId || activeWorkspaceId || workspaces[0]?.id || '');
      setError(null);
      setIsImportMenuOpen(false);
    }
  }, [isOpen, workspaceId, activeWorkspaceId, workspaces]);

  if (!isOpen) return null;

  const cleanName = name.trim();
  const fileName = cleanName ? `${cleanName.replace(/[/\\?%*:|"<>]/g, '_')}.pls` : '';
  const wsPath = currentWorkspace?.path || '';
  const separator = wsPath.includes('\\') ? '\\' : '/';
  const studyFilePath = fileName && wsPath ? `${wsPath.replace(/[/\\]+$/, '')}${separator}${fileName}` : '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cleanName || !currentWorkspace) return;

    setError(null);
    setIsSubmitting(true);
    try {
      const res = await api.addProject(currentWorkspace.path, cleanName);
      if (res.error) {
        setError(res.error);
        setIsSubmitting(false);
        return;
      }

      const projectPath = res.project_path || studyFilePath;
      const newId = projectPath || 'study_' + Date.now();
      addStudy({
        id: newId,
        workspaceId: currentWorkspace.id,
        name: cleanName,
        type: 'PLS-SEM',
        description: '',
        lastModified: 'Just now',
        path: projectPath
      });
      setActiveStudy(newId);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportSmartPls = async (isFolder: boolean) => {
    if (!currentWorkspace) return;
    setError(null);
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open(
        isFolder
          ? {
              directory: true,
              multiple: false,
              title: 'Select SmartPLS Project Folder',
            }
          : {
              directory: false,
              multiple: false,
              title: 'Select SmartPLS Project ZIP',
              filters: [{ name: 'SmartPLS Project ZIP', extensions: ['zip'] }],
            }
      );

      if (!selected || typeof selected !== 'string') return;

      setIsSubmitting(true);
      const detection = await api.detectSmartPls(selected);
      if (!detection?.valid) {
        setError(detection?.error || 'Selected file/folder is not a valid SmartPLS project.');
        setIsSubmitting(false);
        return;
      }

      const res = await api.importSmartPls(selected, currentWorkspace.path, currentWorkspace.name);
      if (res?.error) {
        setError(res.error);
        setIsSubmitting(false);
        return;
      }

      if (res?.studies) {
        const state = useStore.getState();
        for (const s of res.studies) {
          state.addStudy({
            ...s,
            workspaceId: currentWorkspace.id,
          });
          try {
            const dataRes = await api.loadProjectData(s.path);
            if (dataRes && Array.isArray(dataRes.columns) && Array.isArray(dataRes.rows)) {
              const parsed = processData(dataRes.dataset_name || s.name, dataRes.columns, dataRes.rows);
              state.setStudyDataset(s.id, parsed);
            }
          } catch (e) {
            console.warn('Could not load data for study', s.name, e);
          }
        }
        if (res.studies.length > 0) {
          state.setActiveStudy(res.studies[0].id);
        }
      }

      if (res?.models && res.models.length > 0) {
        const state = useStore.getState();
        for (const m of res.models) {
          state.addModel({
            id: m.id,
            studyId: m.studyId,
            name: m.name,
            type: m.type || 'pls',
            lastModified: 'Just now',
          });
        }
      }
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to import SmartPLS project');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay active" style={{ display: 'flex' }} onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal__header">
          <h2 className="modal__title">Import / New Study</h2>
          <button className="icon-btn icon-btn--sm" type="button" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal__body">
            {workspaces.length > 1 && (
              <div className="modal__field">
                <label className="modal__label" htmlFor="study-workspace">Workspace</label>
                <select
                  id="study-workspace"
                  className="modal__input"
                  value={currentWorkspaceId || ''}
                  onChange={e => setSelectedWorkspaceId(e.target.value)}
                >
                  {workspaces.map(ws => (
                    <option key={ws.id} value={ws.id}>{ws.name}</option>
                  ))}
                </select>
              </div>
            )}

            <div className="modal__field">
              <label className="modal__label" htmlFor="study-name">Study Name</label>
              <input
                type="text"
                id="study-name"
                className="modal__input"
                placeholder="e.g. Technology Acceptance Model"
                value={name}
                onChange={e => setName(e.target.value)}
                autoFocus
              />
            </div>

            {studyFilePath && (
              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', wordBreak: 'break-all' }}>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{studyFilePath}</span>
              </div>
            )}

            {error && (
              <div style={{ color: 'var(--color-danger, #ef4444)', fontSize: '12px' }}>{error}</div>
            )}

            <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid var(--color-border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                Or import project
              </span>
              <div style={{ position: 'relative' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsImportMenuOpen(open => !open)}
                  disabled={isSubmitting}
                  style={{
                    padding: '6px 12px',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-border-subtle)',
                    background: 'var(--color-bg-base)',
                    color: 'var(--color-text-primary)',
                    cursor: 'pointer',
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>file_download</span>
                  <span>Import Project</span>
                  <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>expand_more</span>
                </button>
                {isImportMenuOpen && (
                  <div
                    style={{
                      position: 'absolute',
                      right: 0,
                      top: 'calc(100% + 4px)',
                      background: 'var(--color-bg-surface)',
                      border: '1px solid var(--color-border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      boxShadow: 'var(--shadow-dropdown)',
                      zIndex: 100,
                      minWidth: '170px',
                      padding: '4px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '2px',
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setIsImportMenuOpen(false);
                        handleImportSmartPls(false);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '8px 10px',
                        fontSize: '12px',
                        borderRadius: 'var(--radius-sm)',
                        border: 'none',
                        background: 'transparent',
                        color: 'var(--color-text-primary)',
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-bg-hover)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>folder_zip</span>
                      <span>From ZIP Archive (.zip)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setIsImportMenuOpen(false);
                        handleImportSmartPls(true);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '8px 10px',
                        fontSize: '12px',
                        borderRadius: 'var(--radius-sm)',
                        border: 'none',
                        background: 'transparent',
                        color: 'var(--color-text-primary)',
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-bg-hover)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>folder</span>
                      <span>From Folder</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="modal__footer">
            <button className="modal__btn-cancel" type="button" onClick={onClose} disabled={isSubmitting}>Cancel</button>
            <button className="modal__btn-create" type="submit" disabled={!cleanName || !currentWorkspaceId || isSubmitting}>
              {isSubmitting ? 'Creating…' : 'Create Study'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default StudyModal;
