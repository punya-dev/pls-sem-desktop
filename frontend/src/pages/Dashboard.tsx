import React, { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import WorkspaceModal from '../components/WorkspaceModal';
import StudyModal from '../components/StudyModal';
import InputDialog from '../components/InputDialog';
import { DataManagerModal } from '../components/DataManagerModal';
import { parseDatasetFile } from '../utils/dataset-parser';
import type { ParsedDataset } from '../utils/dataset-parser';

const Dashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { 
    workspaces, archivedWorkspaces, activeWorkspaceId, setActiveWorkspace,
    studies, setActiveStudy, models, setActiveModel, addModel,
    datasetsByStudy, setStudyDataset, touchStudy, archiveWorkspace, restoreWorkspace, renameWorkspace,
    deleteWorkspace, deleteStudy, deleteModel, deleteDataset, requestDelete,
    renameStudy, duplicateStudy, renameModel, duplicateModel, openTab
  } = useStore();
  
  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length > 0) {
      setActiveWorkspace(workspaces[0].id);
    }
  }, [activeWorkspaceId, workspaces, setActiveWorkspace]);

  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isWorkspaceSearchOpen, setIsWorkspaceSearchOpen] = useState(false);
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const [isStudySearchOpen, setIsStudySearchOpen] = useState(false);
  const [studyQuery, setStudyQuery] = useState('');
  const [expandedStudies, setExpandedStudies] = useState<Set<string>>(new Set());
  
  const [isStudyModalOpen, setIsStudyModalOpen] = useState(false);
  const [inputDialogConfig, setInputDialogConfig] = useState<{isOpen: boolean; title: string; placeholder: string; submitLabel: string; initialValue?: string; onSubmit: (val: string) => void}>({
    isOpen: false, title: '', placeholder: '', submitLabel: '', onSubmit: () => {}
  });
  
  const [isModelModalOpen, setModelModalOpen] = useState(false);
  const [modelModalStudyId, setModelModalStudyId] = useState<string>('');
  const [modelName, setModelName] = useState('');
  const [modelType, setModelType] = useState('PLS-SEM');

  const activeWorkspace = workspaces.find(w => w.id === activeWorkspaceId);
  const activeStudies = studies.filter(s => s.workspaceId === activeWorkspaceId);
  const filteredWorkspaces = workspaces.filter(workspace => workspace.name.toLocaleLowerCase().includes(workspaceQuery.toLocaleLowerCase()));
  const filteredStudies = activeStudies.filter(study => study.name.toLocaleLowerCase().includes(studyQuery.toLocaleLowerCase()));

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [datasetToImport, setDatasetToImport] = useState<ParsedDataset | null>(null);
  const [importingStudyId, setImportingStudyId] = useState<string | null>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const parsed = await parseDatasetFile(file);
      setDatasetToImport(parsed);
    } catch (err) {
      alert("Error importing file: " + err);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleImportComplete = (dataset: ParsedDataset) => {
    if (!importingStudyId) return;
    setStudyDataset(importingStudyId, dataset);
    touchStudy(importingStudyId);
    setDatasetToImport(null);
    setImportingStudyId(null);
  };



  const handleCreateStudy = () => {
    setIsStudyModalOpen(true);
  };

  const toggleStudy = (studyId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newExpanded = new Set(expandedStudies);
    if (newExpanded.has(studyId)) {
      newExpanded.delete(studyId);
    } else {
      newExpanded.add(studyId);
    }
    setExpandedStudies(newExpanded);
  };

  const openModelModal = (studyId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setModelModalStudyId(studyId);
    setModelName('');
    setModelType('PLS-SEM');
    setModelModalOpen(true);
  };

  const rename = (title: string, initialValue: string, onSubmit: (name: string) => void) => {
    setInputDialogConfig({ isOpen: true, title, placeholder: 'Enter a name', submitLabel: 'Save', initialValue, onSubmit });
  };

  const handleCreateModel = () => {
    if (modelName.trim() && modelModalStudyId) {
      const id = 'model' + Date.now();
      addModel({
        id,
        studyId: modelModalStudyId,
        name: modelName.trim(),
        type: modelType,
        lastModified: 'Just now'
      });
      setModelModalOpen(false);
      setActiveStudy(modelModalStudyId);
      setActiveModel(id);
      openTab({
        type: 'model',
        title: modelName.trim(),
        modelId: id,
        studyId: modelModalStudyId,
        workspaceId: activeWorkspaceId,
      });
    }
  };

  return (
    <>
      <div className="app-body">
        
        <aside className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`} id="sidebar">
          <div className="sidebar__top">
            <div className="sidebar-ws-container">
              <div className="sidebar-header" style={{paddingBottom: '10px', borderBottom: 'none'}}>
                {isWorkspaceSearchOpen ? <div className="inline-search-wrap"><input autoFocus className="sidebar-inline-search" value={workspaceQuery} onChange={event => setWorkspaceQuery(event.target.value)} onBlur={() => { if (!workspaceQuery) setIsWorkspaceSearchOpen(false); }} placeholder="Filter workspaces…" />{workspaceQuery && <button className="inline-search-clear" type="button" aria-label="Clear workspace search" onMouseDown={event => event.preventDefault()} onClick={() => setWorkspaceQuery('')}>×</button>}</div> : <span className="sidebar-header__label">Workspaces</span>}
                <div className="sidebar-header__actions">
                  <button className={`icon-btn icon-btn--sm ${isWorkspaceSearchOpen ? 'active' : ''}`} title="Filter workspaces" type="button" onClick={() => { setIsWorkspaceSearchOpen(open => !open); if (isWorkspaceSearchOpen) setWorkspaceQuery(''); }}>
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

              <div id="sidebar-ws-list" style={{display: 'flex', flexDirection: 'column', gap: '2px'}}>
                {filteredWorkspaces.map(ws => (
                  <button 
                    key={ws.id} 
                    className={`sidebar-item ${ws.id === activeWorkspaceId ? 'active' : ''}`}
                    type="button"
                    onClick={() => {
                      setActiveWorkspace(ws.id);
                      openTab({ type: 'workspace', title: ws.name, workspaceId: ws.id });
                    }}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      useStore.getState().openContextMenu(e.clientX, e.clientY, [
                        {
                          id: 'rename', label: 'Rename Workspace', icon: 'edit', action: () => rename('Rename Workspace', ws.name, name => renameWorkspace(ws.id, name))
                        },
                        {
                          id: 'duplicate', label: 'Duplicate Workspace', icon: 'content_copy', action: () => useStore.getState().addWorkspace({ ...ws, id: `ws_${Date.now()}`, name: `${ws.name} copy` })
                        },
                        {
                          id: 'archive', label: 'Archive Workspace', icon: 'inventory_2', action: () => archiveWorkspace(ws.id)
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
                              message: 'Are you sure? This workspace and all its contents will be permanently deleted and cannot be recovered.',
                              onConfirm: () => deleteWorkspace(ws.id),
                            });
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
                {isWorkspaceSearchOpen && workspaceQuery && filteredWorkspaces.length === 0 && <span className="inline-search-empty">No workspaces found</span>}
              </div>
            </div>
          </div>

          <div className="sidebar__bottom">
            <button className="sidebar-item" type="button" data-action="archive" onClick={() => openTab({ id: 'tab-archive', type: 'archive', title: 'Archive' })}>
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
                <span className="truncate">Feedback & Reports</span>
              </span>
            </button>
          </div>
        </aside>

        <main className="ws-main">
          <div className="ws-inner">
            
            <div className="ws-header animate-fade-in">
              <div className="ws-header__left">
                <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-accent, #6B4EE6)', letterSpacing: '-0.02em', margin: 0 }}>
                  {activeWorkspace?.name || 'Workspace'}
                </h1>
              </div>
              <div className="ws-header__actions">
                <button className="btn-ws-primary" type="button" onClick={handleCreateStudy}>
                  <span className="material-symbols-outlined">add</span>
                  <span>New Study</span>
                  <kbd className="kbd">⌘S</kbd>
                </button>
              </div>
            </div>

            <div style={{flex: '1', display: 'flex', flexDirection: 'column'}}>
              <div className="studies-header">
                <div className="studies-header__left" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {isStudySearchOpen ? <div className="inline-search-wrap"><input autoFocus className="studies-inline-search" value={studyQuery} onChange={event => setStudyQuery(event.target.value)} onBlur={() => { if (!studyQuery) setIsStudySearchOpen(false); }} placeholder="Filter studies…" />{studyQuery && <button className="inline-search-clear" type="button" aria-label="Clear study search" onMouseDown={event => event.preventDefault()} onClick={() => setStudyQuery('')}>×</button>}</div> : <span style={{ color: 'var(--color-text-secondary)' }}>Studies</span>}
                  <button type="button" style={{padding: '2px', borderRadius: 'var(--radius-sm)', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', background: 'transparent', cursor: 'pointer'}} title="Filter studies" onClick={() => { setIsStudySearchOpen(open => !open); if (isStudySearchOpen) setStudyQuery(''); }}>
                    <span className="material-symbols-outlined" style={{fontSize: '15px'}}>search</span>
                  </button>
                </div>
                <div style={{display: 'flex', alignItems: 'center', gap: '32px'}}>
                  <div className="studies-header__sort" onClick={() => setInputDialogConfig({isOpen: true, title: 'Filter by Modified', placeholder: 'Enter filter query...', submitLabel: 'Apply Filter', onSubmit: () => {}})} style={{ cursor: 'pointer', color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>Modified</span>
                    <span className="material-symbols-outlined" style={{fontSize: '15px'}}>filter_list</span>
                  </div>
                  <span style={{width: '16px'}}></span>
                </div>
              </div>

              <div className="studies-list" id="studies-container">
                {filteredStudies.length === 0 && (
                  <div className="empty-state animate-fade-in" style={{ padding: '32px 16px', textAlign: 'center' }}>
                    <div style={{fontSize: 'var(--text-md)', color: studyQuery ? 'var(--color-danger)' : 'var(--color-text-secondary)'}}>{studyQuery ? 'No studies found' : 'Create a new study to get started.'}</div>
                  </div>
                )}
                
                {filteredStudies.map(study => {
                  const studyModels = models.filter(m => m.studyId === study.id);
                  const studyDataset = datasetsByStudy[study.id];
                  const isEmpty = studyModels.length === 0 && !studyDataset;
                  const isExpanded = expandedStudies.has(study.id);
                  
                  return (
                    <div key={study.id} className="study-entry">
                          <div 
                            key={study.id} 
                            className="study-row" 
                            onClick={(e) => toggleStudy(study.id, e)}
                            onContextMenu={(e) => {
                              e.preventDefault();
                              useStore.getState().openContextMenu(e.clientX, e.clientY, [
                                {
                                  id: 'create-model', label: 'Create Model', icon: 'add', action: () => { setModelModalStudyId(study.id); setModelName(''); setModelType('PLS-SEM'); setModelModalOpen(true); }
                                },
                                ...(!studyDataset ? [{ id: 'add-dataset', label: 'Add Dataset', icon: 'upload_file', action: () => { setImportingStudyId(study.id); fileInputRef.current?.click(); } }] : []),
                                { id: 'rename', label: 'Rename Study', icon: 'edit', action: () => rename('Rename Study', study.name, name => renameStudy(study.id, name)) },
                                { id: 'duplicate', label: 'Duplicate Study', icon: 'content_copy', action: () => duplicateStudy(study.id) },
                                {
                                  id: 'delete', 
                                  label: 'Delete Study', 
                                  icon: 'delete', 
                                  danger: true, 
                                  action: () => {
                                    requestDelete({
                                      title: 'Delete Study',
                                      itemName: study.name,
                                      message: 'Are you sure? This study and all its models and datasets will be permanently deleted and cannot be recovered.',
                                      onConfirm: () => deleteStudy(study.id),
                                    });
                                  } 
                                }
                              ]);
                            }}
                          >
                        <div className="study-row__left">
                          <span className="material-symbols-outlined study-folder" style={isEmpty ? {color: 'var(--color-text-hint)', fontVariationSettings: "'FILL' 0"} : {}}>
                            {isExpanded && !isEmpty ? 'folder_open' : 'folder'}
                          </span>
                          <span className="study-row__name" style={isEmpty ? {color: 'var(--color-text-secondary)', fontWeight: 400} : {}}>
                            {study.name}
                          </span>
                          <span className="study-row__count">
                            {isEmpty ? 'Empty' : `${studyModels.length + (studyDataset ? 1 : 0)} item${studyModels.length + (studyDataset ? 1 : 0) === 1 ? '' : 's'}`}
                          </span>
                          {isEmpty && (
                            <div className="study-row__actions">
                              <button className="btn-inline" type="button" onClick={(e) => { e.stopPropagation(); setImportingStudyId(study.id); fileInputRef.current?.click(); }}><span className="material-symbols-outlined">upload_file</span><span>Import Dataset</span></button>
                              <span style={{color: 'rgba(0,0,0,0.15)'}}>•</span>
                              <button className="btn-inline" type="button" onClick={(e) => openModelModal(study.id, e)}><span className="material-symbols-outlined">add</span><span>Create Model</span></button>
                            </div>
                          )}
                        </div>
                        <div className="study-row__meta">
                          <span className="study-row__time">{study.lastModified}</span>
                          <span className="study-row__chevron">
                            <span className="material-symbols-outlined study-chevron" style={{transform: isExpanded || isEmpty ? 'rotate(0deg)' : 'rotate(-90deg)'}}>
                              {isExpanded && !isEmpty ? 'expand_more' : 'chevron_right'}
                            </span>
                          </span>
                        </div>
                      </div>
                      
                      <div className={`study-children ${!isExpanded ? 'hidden' : ''}`} id={`study-children-${study.id}`}>
                        {isEmpty ? (
                          <div style={{padding: '12px 16px', marginLeft: '26px', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', fontStyle: 'italic'}}>
                            No files yet. Drop files here to get started.
                          </div>
                        ) : (
                          <>
                            {studyDataset && (
                              <div className="file-row file-row--muted" onClick={() => { setImportingStudyId(study.id); setDatasetToImport(studyDataset); }} onContextMenu={e => { e.preventDefault(); e.stopPropagation(); useStore.getState().openContextMenu(e.clientX, e.clientY, [{ id: 'rename', label: 'Rename Dataset', icon: 'edit', action: () => rename('Rename Dataset', studyDataset.filename, name => { setStudyDataset(study.id, { ...studyDataset, filename: name }); touchStudy(study.id); }) }, { id: 'delete', label: 'Delete Dataset', icon: 'delete', danger: true, action: () => { requestDelete({ title: 'Delete Dataset', itemName: studyDataset.filename, message: 'Are you sure? This dataset will be permanently deleted and cannot be recovered.', onConfirm: () => { deleteDataset(study.id); touchStudy(study.id); } }); } }]); }}>
                                <div className="file-row__left"><span className="material-symbols-outlined">dataset</span><span>{studyDataset.filename}</span><span className="file-badge file-badge--default">{studyDataset.rows.length} rows</span><span className="file-badge file-badge--default">Dataset</span></div>
                                <div className="file-row__meta"><span className="file-row__time">{study.lastModified}</span><span style={{width: '16px'}}></span></div>
                              </div>
                            )}
                            {studyModels.map(model => (
                              <div key={model.id} className="file-row" onClick={() => {
                                setActiveStudy(study.id);
                                setActiveModel(model.id);
                                openTab({
                                  type: 'model',
                                  title: model.name,
                                  modelId: model.id,
                                  studyId: study.id,
                                  workspaceId: activeWorkspaceId,
                                });
                              }} onContextMenu={e => { e.preventDefault(); e.stopPropagation(); useStore.getState().openContextMenu(e.clientX, e.clientY, [{ id: 'rename', label: 'Rename Model', icon: 'edit', action: () => rename('Rename Model', model.name, name => renameModel(model.id, name)) }, { id: 'duplicate', label: 'Duplicate Model', icon: 'content_copy', action: () => duplicateModel(model.id) }, { id: 'delete', label: 'Delete Model', icon: 'delete', danger: true, action: () => { requestDelete({ title: 'Delete Model', itemName: model.name, message: 'Are you sure? This model will be permanently deleted and cannot be recovered.', onConfirm: () => deleteModel(model.id) }); } }]); }}>
                                <div className="file-row__left">
                                  <span className="material-symbols-outlined">{model.type === 'Dataset' ? 'dataset' : 'account_tree'}</span>
                                  <span>{model.name}</span>
                                  <span className={`file-badge ${model.type === 'PLS-SEM' ? 'file-badge--accent' : (model.type === 'Dataset' ? 'file-badge--default' : '')}`}>{model.type}</span>
                                </div>
                                <div className="file-row__meta">
                                  <span className="file-row__time">{model.lastModified}</span>
                                  <span style={{width: '16px'}}></span>
                                </div>
                              </div>
                            ))}
                            <div style={{display: 'flex', gap: '16px', margin: '8px 0 8px 26px'}}>
                              <div className="create-model-link" onClick={(e) => openModelModal(study.id, e)} style={{margin: 0, padding: 0}}><span className="material-symbols-outlined">add</span><span>Create Model</span></div>
                              {!studyDataset && <div className="create-model-link" style={{margin: 0, padding: 0}} onClick={(e) => { e.stopPropagation(); setImportingStudyId(study.id); fileInputRef.current?.click(); }}><span className="material-symbols-outlined">upload_file</span><span>Import Dataset</span></div>}
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </main>
      </div>
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileUpload} 
        style={{ display: 'none' }} 
        accept=".csv,.xlsx,.xls,.sav"
      />

      <WorkspaceModal isOpen={isWorkspaceModalOpen} onClose={() => setIsWorkspaceModalOpen(false)} />
      <StudyModal 
        isOpen={isStudyModalOpen} 
        onClose={() => setIsStudyModalOpen(false)} 
        workspaceId={activeWorkspaceId || ''} 
      />
      <InputDialog 
        isOpen={inputDialogConfig.isOpen} 
        onClose={() => setInputDialogConfig(prev => ({...prev, isOpen: false}))}
        title={inputDialogConfig.title}
        placeholder={inputDialogConfig.placeholder}
        submitLabel={inputDialogConfig.submitLabel}
        initialValue={inputDialogConfig.initialValue}
        onSubmit={inputDialogConfig.onSubmit}
      />

      {isModelModalOpen && (
      <div className="modal-overlay active" id="modal-model-overlay" style={{display: 'flex'}}>
        <div className="modal">
          <div className="modal__header">
            <div className="modal__title">Create New Model</div>
            <button className="icon-btn icon-btn--sm" onClick={() => setModelModalOpen(false)} type="button">
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <div className="modal__body">
            <div className="modal__field">
              <label className="modal__label" htmlFor="modal-model-study">Study</label>
              <div style={{display: 'flex', gap: '8px'}}>
                <select className="modal__input" id="modal-model-study" style={{flex: '1', cursor: 'pointer'}} value={modelModalStudyId} onChange={(e) => setModelModalStudyId(e.target.value)}>
                  {activeStudies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </div>
            <div className="modal__field">
              <label className="modal__label" htmlFor="modal-model-name">Model Name</label>
              <input className="modal__input" id="modal-model-name" value={modelName} onChange={e => setModelName(e.target.value)} type="text" placeholder="e.g., Structural Model" autoComplete="off" spellCheck="false" autoFocus />
            </div>
            <div className="modal__field">
              <label className="modal__label" htmlFor="modal-model-type">Model Type</label>
              <select className="modal__input" id="modal-model-type" value={modelType} onChange={e => setModelType(e.target.value)} style={{cursor: 'pointer'}}>
                <option value="PLS-SEM">PLS-SEM</option>
                <option value="CB-SEM">CB-SEM</option>
                <option value="Regression">Regression</option>
              </select>
            </div>
            <div className="modal__field">
              <label className="modal__label">Dataset</label>
              {datasetsByStudy[modelModalStudyId] ? (
                <div className="modal__input" style={{background: 'var(--color-bg-subtle)', color: 'var(--color-text-secondary)'}}>{datasetsByStudy[modelModalStudyId].filename}</div>
              ) : (
                <button className="modal__browse-btn" type="button" onClick={() => { setImportingStudyId(modelModalStudyId); fileInputRef.current?.click(); }}>Add dataset</button>
              )}
            </div>
          </div>
          <div className="modal__footer">
            <button className="modal__btn-cancel" id="modal-model-cancel-btn" type="button" onClick={() => setModelModalOpen(false)}>Cancel</button>
            <button className="modal__btn-create" id="modal-model-create-btn" type="button" disabled={!modelName.trim() || !modelModalStudyId} onClick={handleCreateModel}>Create Model</button>
          </div>
        </div>
      </div>
      )}

      {datasetToImport && (
        <DataManagerModal
          dataset={datasetToImport}
          onImport={handleImportComplete}
          onCancel={() => setDatasetToImport(null)}
        />
      )}
    </>
  );
};

export default Dashboard;
