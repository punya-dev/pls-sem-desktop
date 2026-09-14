import React, { useState, useEffect } from 'react';
import { useStore } from '../store';
import { api } from '../utils/api';

interface StudyModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
}

const StudyModal = ({ isOpen, onClose, workspaceId }: StudyModalProps) => {
  const [name, setName] = useState('');
  const [type, setType] = useState('PLS-SEM');
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(workspaceId);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { workspaces, activeWorkspaceId, addStudy, setActiveStudy } = useStore();
  const currentWorkspaceId = selectedWorkspaceId || workspaceId || activeWorkspaceId;
  const currentWorkspace = workspaces.find(w => w.id === currentWorkspaceId);

  useEffect(() => {
    if (isOpen) {
      setName('');
      setType('PLS-SEM');
      setSelectedWorkspaceId(workspaceId || activeWorkspaceId || workspaces[0]?.id || '');
      setError(null);
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
        type: type,
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

  return (
    <div className="modal-overlay active" style={{ display: 'flex' }} onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal__header">
          <h2 className="modal__title">Create New Study</h2>
          <button className="icon-btn icon-btn--sm" type="button" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal__body">
            <div className="modal__field">
              <label className="modal__label" htmlFor="study-workspace">Workspace</label>
              <select
                id="study-workspace" 
                className="modal__input" 
                value={currentWorkspaceId || ''}
                onChange={e => setSelectedWorkspaceId(e.target.value)}
                disabled={workspaces.length === 0}
              >
                {workspaces.length === 0 ? (
                  <option value="">No workspaces available</option>
                ) : (
                  workspaces.map(workspace => (
                    <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                  ))
                )}
              </select>
            </div>

            <div className="modal__field">
              <label className="modal__label" htmlFor="study-type">Model Type</label>
              <select 
                id="study-type" 
                className="modal__input" 
                value={type}
                onChange={e => setType(e.target.value)}
              >
                <option value="PLS-SEM">PLS-SEM</option>
                <option value="CB-SEM">CB-SEM</option>
                <option value="Regression">Regression</option>
              </select>
            </div>

            <div className="modal__field">
              <label className="modal__label" htmlFor="study-name">Study Name <span style={{color: 'var(--color-red)'}}>*</span></label>
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
              <div style={{
                marginTop: '14px',
                fontSize: '11px',
                color: 'var(--color-text-muted)',
                wordBreak: 'break-all'
              }}>
                Project file: <span style={{ fontFamily: 'var(--font-mono)' }}>{studyFilePath}</span>
              </div>
            )}

            {error && (
              <div style={{ color: 'var(--color-danger, #ef4444)', fontSize: '12px', marginTop: '10px' }}>
                {error}
              </div>
            )}
          </div>
          <div className="modal__footer">
            <button className="modal__btn-cancel" type="button" onClick={onClose} disabled={isSubmitting}>Cancel</button>
            <button className="modal__btn-create" type="submit" disabled={!cleanName || !currentWorkspaceId || isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create Study'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default StudyModal;
