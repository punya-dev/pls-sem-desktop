import React, { useState } from 'react';
import { useStore } from '../store';
import { api } from '../utils/api';
import { processData } from '../utils/dataset-parser';

interface ImportWorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ImportWorkspaceModal: React.FC<ImportWorkspaceModalProps> = ({ isOpen, onClose }) => {
  const { workspaces, addWorkspace, setActiveWorkspace, openTab, addStudy } = useStore();

  const [step, setStep] = useState<'pick' | 'destination'>('pick');
  const [selectedPath, setSelectedPath] = useState<string>('');
  const [detection, setDetection] = useState<{
    valid?: boolean;
    project_name?: string;
    models_count?: number;
    datasets_count?: number;
    models?: Array<{ file: string; name: string }>;
    datasets?: string[];
  } | null>(null);

  const [destinationMode, setDestinationMode] = useState<'new' | 'existing'>('new');
  const [newWsName, setNewWsName] = useState<string>('');
  const [selectedWsId, setSelectedWsId] = useState<string>(workspaces[0]?.id || '');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleReset = () => {
    setStep('pick');
    setSelectedPath('');
    setDetection(null);
    setDestinationMode('new');
    setNewWsName('');
    setIsProcessing(false);
    setError(null);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSelectFolder = async () => {
    setError(null);
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: true,
        multiple: false,
        title: 'Select Workspace Folder or SmartPLS Project Folder',
      });

      if (!selected || typeof selected !== 'string') return;
      await processSelectedPath(selected, true);
    } catch (err: any) {
      console.warn('Tauri open error, fallback to prompt:', err);
      const fallback = window.prompt('Enter folder path:');
      if (fallback) {
        await processSelectedPath(fallback.trim(), true);
      }
    }
  };

  const handleSelectZip = async () => {
    setError(null);
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({
        directory: false,
        multiple: false,
        title: 'Select SmartPLS Project ZIP Archive',
        filters: [{ name: 'SmartPLS ZIP Archive', extensions: ['zip'] }],
      });

      if (!selected || typeof selected !== 'string') return;
      await processSelectedPath(selected, false);
    } catch (err: any) {
      console.warn('Tauri open error, fallback to prompt:', err);
      const fallback = window.prompt('Enter ZIP file path:');
      if (fallback) {
        await processSelectedPath(fallback.trim(), false);
      }
    }
  };

  const processSelectedPath = async (path: string, isFolder: boolean) => {
    setIsProcessing(true);
    setError(null);
    try {
      // 1. Detect if it is a SmartPLS project
      const det = await api.detectSmartPls(path);
      if (det && det.valid) {
        // It's a SmartPLS project!
        setSelectedPath(path);
        setDetection(det);
        setNewWsName(det.project_name || 'SmartPLS Workspace');
        if (workspaces.length > 0) {
          setSelectedWsId(workspaces[0].id);
        }
        setStep('destination');
        setIsProcessing(false);
        return;
      }

      // 2. If it's a folder and not SmartPLS, open as normal CSPLS workspace
      if (isFolder) {
        const res = await api.openWorkspace(path);
        if (res?.error) {
          setError(res.error);
          setIsProcessing(false);
          return;
        }

        const wsName =
          res?.workspace?.name ||
          path.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() ||
          'Workspace';

        const existing = workspaces.find((w) => w.path === path);
        const wsId = existing ? existing.id : path;

        if (!existing) {
          addWorkspace({
            id: wsId,
            name: wsName,
            path: path,
            createdAt: new Date().toISOString(),
            modifiedAt: new Date().toISOString(),
          });
        }

        setActiveWorkspace(wsId);
        openTab({ type: 'workspace', title: wsName, workspaceId: wsId });
        handleClose();
        return;
      }

      // If it was a ZIP file and detection failed
      setError('The selected ZIP file does not contain a valid SmartPLS export.');
    } catch (err: any) {
      setError(err?.message || 'Failed to inspect selected path.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!selectedPath || !detection) return;
    setIsProcessing(true);
    setError(null);

    try {
      let targetWsPath: string | undefined = undefined;
      let targetWsName: string | undefined = undefined;

      if (destinationMode === 'existing') {
        const existing = workspaces.find((w) => w.id === selectedWsId);
        if (!existing) {
          setError('Please select an existing workspace.');
          setIsProcessing(false);
          return;
        }
        targetWsPath = existing.path;
        targetWsName = existing.name;
      } else {
        targetWsName = newWsName.trim() || detection.project_name || 'Imported Workspace';
      }

      const res = await api.importSmartPls(selectedPath, targetWsPath, targetWsName);
      if (res?.error) {
        setError(res.error);
        setIsProcessing(false);
        return;
      }

      const ws = res.workspace;
      if (ws) {
        const existing = workspaces.find((w) => w.path === ws.path || w.id === ws.id);
        const finalWsId = existing ? existing.id : ws.id || ws.path;

        if (!existing) {
          addWorkspace({
            id: finalWsId,
            name: ws.name || targetWsName || 'Workspace',
            path: ws.path,
            createdAt: ws.createdAt || new Date().toISOString(),
            modifiedAt: ws.modifiedAt || new Date().toISOString(),
          });
        }

        if (res.studies) {
          for (const s of res.studies) {
            addStudy({
              ...s,
              workspaceId: finalWsId,
            });
            try {
              const dataRes = await api.loadProjectData(s.path);
              if (dataRes && Array.isArray(dataRes.columns) && Array.isArray(dataRes.rows)) {
                const parsed = processData(dataRes.dataset_name || s.name, dataRes.columns, dataRes.rows);
                useStore.getState().setStudyDataset(s.id, parsed);
              }
            } catch (e) {
              console.warn('Could not load data for study', s.name, e);
            }
          }
          if (res.studies.length > 0) {
            useStore.getState().setActiveStudy(res.studies[0].id);
          }
        }

        if (res.models && res.models.length > 0) {
          for (const m of res.models) {
            useStore.getState().addModel({
              id: m.id,
              studyId: m.studyId,
              name: m.name,
              type: m.type || 'pls',
              lastModified: 'Just now',
            });
          }
        }

        setActiveWorkspace(finalWsId);
        openTab({ type: 'workspace', title: ws.name || targetWsName || 'Workspace', workspaceId: finalWsId });
      }

      handleClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to complete project import.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="modal-overlay active" style={{ display: 'flex' }} onClick={handleClose}>
      <div className="modal" style={{ maxWidth: '480px', width: '100%' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h2 className="modal__title">
            {step === 'pick' ? 'Import Workspace or Project' : 'Import SmartPLS Project'}
          </h2>
          <button className="icon-btn icon-btn--sm" type="button" onClick={handleClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="modal__body">
          {error && (
            <div style={{ color: 'var(--color-danger, #ef4444)', fontSize: '12px', marginBottom: '12px' }}>
              {error}
            </div>
          )}

          {step === 'pick' && (
            <div>
              <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', margin: '0 0 16px 0', lineHeight: 1.5 }}>
                Open an existing CSPLS workspace folder, or directly select an exported SmartPLS project folder or ZIP archive.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleSelectFolder}
                  disabled={isProcessing}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-border-subtle)',
                    background: 'var(--color-bg-base)',
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '24px', color: 'var(--color-accent)' }}>
                    folder_open
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                      Choose Folder
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                      Select a CSPLS workspace folder or SmartPLS export directory
                    </div>
                  </div>
                </button>

                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleSelectZip}
                  disabled={isProcessing}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-border-subtle)',
                    background: 'var(--color-bg-base)',
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '24px', color: 'var(--color-accent)' }}>
                    folder_zip
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                      Choose ZIP Archive
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                      Select a SmartPLS project exported as a .zip file
                    </div>
                  </div>
                </button>
              </div>

              {isProcessing && (
                <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '14px', textAlign: 'center' }}>
                  Inspecting selection…
                </div>
              )}
            </div>
          )}

          {step === 'destination' && detection && (
            <div>
              <div
                style={{
                  padding: '10px 12px',
                  background: 'var(--color-bg-subtle, rgba(255,255,255,0.03))',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border-subtle)',
                  marginBottom: '16px',
                }}
              >
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: '4px' }}>
                  {detection.project_name}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                  Detected: {detection.models_count || 0} model(s), {detection.datasets_count || 0} dataset(s)
                </div>
              </div>

              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: '10px' }}>
                Where would you like to import this project?
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="destMode"
                    checked={destinationMode === 'new'}
                    onChange={() => setDestinationMode('new')}
                    style={{ marginTop: '2px' }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-text-primary)' }}>
                      Create a New Workspace
                    </div>
                    {destinationMode === 'new' && (
                      <input
                        type="text"
                        className="modal__input"
                        placeholder="Workspace name"
                        value={newWsName}
                        onChange={(e) => setNewWsName(e.target.value)}
                        style={{ marginTop: '6px', width: '100%' }}
                        autoFocus
                      />
                    )}
                  </div>
                </label>

                <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="destMode"
                    checked={destinationMode === 'existing'}
                    onChange={() => setDestinationMode('existing')}
                    disabled={workspaces.length === 0}
                    style={{ marginTop: '2px' }}
                  />
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontSize: '12px',
                        fontWeight: 500,
                        color: workspaces.length === 0 ? 'var(--color-text-muted)' : 'var(--color-text-primary)',
                      }}
                    >
                      Import into an Existing Workspace {workspaces.length === 0 && '(none available)'}
                    </div>
                    {destinationMode === 'existing' && workspaces.length > 0 && (
                      <select
                        className="modal__input"
                        value={selectedWsId}
                        onChange={(e) => setSelectedWsId(e.target.value)}
                        style={{ marginTop: '6px', width: '100%' }}
                      >
                        {workspaces.map((ws) => (
                          <option key={ws.id} value={ws.id}>
                            {ws.name} ({ws.path})
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </label>
              </div>
            </div>
          )}
        </div>

        <div className="modal__footer">
          {step === 'destination' ? (
            <>
              <button className="modal__btn-cancel" type="button" onClick={() => setStep('pick')} disabled={isProcessing}>
                Back
              </button>
              <button
                className="modal__btn-create"
                type="button"
                onClick={handleConfirmImport}
                disabled={isProcessing || (destinationMode === 'new' && !newWsName.trim()) || (destinationMode === 'existing' && !selectedWsId)}
              >
                {isProcessing ? 'Importing…' : 'Import Project'}
              </button>
            </>
          ) : (
            <button className="modal__btn-cancel" type="button" onClick={handleClose} disabled={isProcessing}>
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImportWorkspaceModal;
