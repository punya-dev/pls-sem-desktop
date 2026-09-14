import React, { useState } from 'react';
import { useStore } from '../store';
import { useNavigate } from 'react-router-dom';

interface WorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const WorkspaceModal = ({ isOpen, onClose }: WorkspaceModalProps) => {
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const { addWorkspace, setActiveWorkspace } = useStore();
  const navigate = useNavigate();

  if (!isOpen) return null;

  const handleBrowse = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: 'Select Workspace Location'
      });
      if (selected && typeof selected === 'string') {
        setLocation(selected);
        if (!name.trim()) {
          const folderName = selected.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop();
          if (folderName) setName(folderName);
        }
      }
    } catch (err) {
      console.warn('Tauri dialog not available, falling back to prompt:', err);
      const fallback = window.prompt('Enter workspace directory path:', location || '~/CSPLS/Workspaces');
      if (fallback) {
        setLocation(fallback);
        if (!name.trim()) {
          const folderName = fallback.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop();
          if (folderName) setName(folderName);
        }
      }
    }
  };

  const cleanName = name.trim();
  const baseLoc = location.trim() || '~/CSPLS/Workspaces';
  const cleanLoc = baseLoc.replace(/[/\\]+$/, '');
  const lastFolder = cleanLoc.split(/[/\\]/).filter(Boolean).pop();
  const calculatedPath = cleanName ? ((lastFolder === cleanName) ? cleanLoc : `${cleanLoc}/${cleanName}`) : cleanLoc;

  const handleCreateWorkspace = () => {
    if (!cleanName) return;
    
    const newId = 'ws_' + Date.now();
    addWorkspace({
      id: newId,
      name: cleanName,
      path: calculatedPath
    });
    setActiveWorkspace(newId);
    setName('');
    setLocation('');
    onClose();
    navigate('/workspace');
  };

  return (
    <div className="modal-overlay active" id="modal-overlay" style={{'display': 'flex'}}>
      <div className="modal">
        <div className="modal__header">
          <div className="modal__title">Create New Workspace</div>
          <button className="icon-btn icon-btn--sm" onClick={onClose} type="button">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        <div className="modal__body">
          <div className="modal__field">
            <label className="modal__label" htmlFor="modal-workspace-name">Workspace Name</label>
            <input
              className="modal__input"
              id="modal-workspace-name"
              type="text"
              placeholder="e.g., Academic_Research"
              autoComplete="off"
              spellCheck="false"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
             />
          </div>

          <div className="modal__field">
            <label className="modal__label" htmlFor="modal-workspace-location">
              Location
            </label>
            <div className="modal__browse-row">
              <span className="modal__browse-icon material-symbols-outlined">folder_open</span>
              <input
                className="modal__input modal__input--path"
                id="modal-workspace-location"
                type="text"
                placeholder="~/CSPLS/Workspaces"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                spellCheck="false"
               />
              <button className="modal__browse-btn" id="modal-browse-btn" type="button" onClick={handleBrowse}>
                Browse…
              </button>
            </div>
            {cleanName && (
              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '6px', wordBreak: 'break-all' }}>
                Full Path: <span style={{ fontFamily: 'var(--font-mono)' }}>{calculatedPath}</span>
              </div>
            )}
          </div>
        </div>
        <div className="modal__footer">
          <button className="modal__btn-cancel" id="modal-cancel-btn" type="button" onClick={onClose}>Cancel</button>
          <button className="modal__btn-create" id="modal-create-btn" type="button" onClick={handleCreateWorkspace} disabled={!name.trim()}>Create Workspace</button>
        </div>
      </div>
    </div>
  );
};

export default WorkspaceModal;
