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
    datasetsByStudy, setStudyDataset, touchStudy, archiveWorkspace, restoreWorkspace, renameWorkspace, trash,
    trashWorkspace, trashStudy, trashModel, trashDataset, restoreTrashItem, permanentlyDeleteTrashItem,
    renameStudy, duplicateStudy, renameModel, duplicateModel
  } = useStore();
  
  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length > 0) {
      setActiveWorkspace(workspaces[0].id);
    }
  }, [activeWorkspaceId, workspaces, setActiveWorkspace]);

  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [isWorkspaceDropdownOpen, setIsWorkspaceDropdownOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isWorkspaceSearchOpen, setIsWorkspaceSearchOpen] = useState(false);
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const [isStudySearchOpen, setIsStudySearchOpen] = useState(false);
  const [studyQuery, setStudyQuery] = useState('');
  const [showArchive, setShowArchive] = useState(() => new URLSearchParams(location.search).get('panel') === 'archive');
  const [showTrash, setShowTrash] = useState(() => new URLSearchParams(location.search).get('panel') === 'trash');
  const [expandedArchivedWorkspaces, setExpandedArchivedWorkspaces] = useState<Set<string>>(new Set());
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

  const trashPath = (item: typeof trash[number]) => {
    if (item.kind === 'workspace') return '';
    if (item.kind === 'study') return item.workspaceName ?? '';
    return [item.workspaceName, item.studyName].filter(Boolean).join(' / ');
  };

  const trashDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? timestamp.split(',')[0] : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
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
      navigate('/model/' + id);
    }
  };

  return (
    <>
      <header className="titlebar window-drag">
        <div className="titlebar__left no-drag">
          <div className="titlebar__traffic-light-space" aria-hidden="true"></div>
          <div className="brand">
            <svg className="brand__logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
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
          <button className="icon-btn" title="Toggle Theme" type="button">
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
                    onClick={() => { setActiveWorkspace(ws.id); setShowArchive(false); setShowTrash(false); navigate('/workspace'); }}
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
                            if (window.confirm(`Are you sure you want to remove workspace "${ws.name}"?`)) {
                              trashWorkspace(ws.id);
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
                {isWorkspaceSearchOpen && workspaceQuery && filteredWorkspaces.length === 0 && <span className="inline-search-empty">No workspaces found</span>}
              </div>
            </div>
          </div>

          <div className="sidebar__bottom">
            <button className={`sidebar-item ${showArchive ? 'active' : ''}`} type="button" data-action="archive" onClick={() => { setShowArchive(value => !value); setShowTrash(false); }}>
              <span className="sidebar-item__left">
                <span className="material-symbols-outlined">inventory_2</span>
                <span>Archive</span>
              </span>
              <span className="sidebar-item__badge">{archivedWorkspaces.length}</span>
            </button>
            <button className={`sidebar-item ${showTrash ? 'active' : ''}`} type="button" onClick={() => { setShowTrash(value => !value); setShowArchive(false); }}>
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
                <span className="truncate">Feedback & Reports</span>
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

        <main className="ws-main">
          <div className="ws-inner">
            
            <div className="ws-header animate-fade-in">
              <div className="ws-header__left">
                <h1 className="ws-header__greeting">{showArchive ? 'Archived workspaces' : showTrash ? 'Trash' : 'Welcome back,'}</h1>
                {!showArchive && !showTrash && <div className="ws-header__workspace-pill" id="workspace-switcher-btn" title="Switch Workspace" onClick={() => setIsWorkspaceDropdownOpen(!isWorkspaceDropdownOpen)} style={{ position: 'relative' }}>
                  <span className="ws-header__workspace-name" id="current-workspace-name">{activeWorkspace?.name || 'Workspace'}</span>
                  <span className="material-symbols-outlined">expand_more</span>
                  {isWorkspaceDropdownOpen && (
                    <div className="workspace-dropdown" style={{ position: 'absolute', top: '100%', left: 0, marginTop: '8px', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-md)', padding: '4px', zIndex: 10, minWidth: '180px', boxShadow: 'var(--shadow-md)' }}>
                      {workspaces.map(ws => (
                        <div key={ws.id} className="cspls-context-menu-item" onClick={(e) => { e.stopPropagation(); setActiveWorkspace(ws.id); setIsWorkspaceDropdownOpen(false); }}>
                          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>folder</span>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{ws.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>}
                {!showArchive && !showTrash && <><span style={{width: '1px', height: '16px', background: 'var(--color-border-divider)', margin: '0 4px'}}></span>
                  <button type="button" style={{padding: '4px', borderRadius: 'var(--radius-sm)', color: 'var(--color-text-hint)', transition: 'all var(--transition-fast)'}} title="New Workspace" onClick={() => setIsWorkspaceModalOpen(true)}>
                    <span className="material-symbols-outlined" style={{fontSize: '18px'}}>add</span>
                  </button></>}
              </div>
              {!showArchive && !showTrash && <div className="ws-header__actions">
                <button className="btn-ws-primary" type="button" onClick={handleCreateStudy}>
                  <span className="material-symbols-outlined">add</span>
                  <span>New Study</span>
                  <kbd className="kbd">⌘S</kbd>
                </button>
              </div>}
            </div>

            {showTrash ? (
              <div className="studies-list">
                {trash.length ? trash.map(item => <div className="study-entry archive-entry" key={item.id}><div className="study-row trash-row"><div className="study-row__left"><span className="material-symbols-outlined study-folder">{item.kind === 'dataset' ? 'dataset' : item.kind === 'model' ? 'account_tree' : 'folder'}</span><span className="study-row__name">{item.name}</span>{trashPath(item) && <span className="trash-path">{trashPath(item)}</span>}<span className="study-row__count">{item.kind}</span></div><div className="study-row__meta trash-row__meta"><span className="study-row__time">{trashDate(item.deletedAt)}</span><button className="archive-restore-btn trash-action trash-action--restore" data-tooltip={`Deleted on ${item.deletedAt}`} type="button" onClick={() => restoreTrashItem(item.id)}>Restore</button><button className="archive-restore-btn trash-action trash-action--danger" type="button" onClick={() => { if (window.confirm(`Permanently delete ${item.name}? This cannot be undone.`)) permanentlyDeleteTrashItem(item.id); }}>Delete forever</button></div></div></div>) : <div className="empty-state" style={{padding: '32px 16px', textAlign: 'center'}}>Trash is empty.</div>}
              </div>
            ) : showArchive ? (
              <div className="studies-list">
                {archivedWorkspaces.length ? archivedWorkspaces.map(workspace => {
                  const isExpanded = expandedArchivedWorkspaces.has(workspace.id);
                  const archivedStudies = studies.filter(study => study.workspaceId === workspace.id);
                  return <div className="study-entry archive-entry" key={workspace.id}>
                    <div className="study-row" onClick={() => setExpandedArchivedWorkspaces(previous => { const next = new Set(previous); next.has(workspace.id) ? next.delete(workspace.id) : next.add(workspace.id); return next; })}>
                      <div className="study-row__left"><span className="material-symbols-outlined study-folder">{isExpanded ? 'inventory_2' : 'inventory_2'}</span><span className="study-row__name">{workspace.name}</span><span className="study-row__count">Archived</span></div>
                      <div className="study-row__meta"><button className="archive-restore-btn" type="button" onClick={event => { event.stopPropagation(); restoreWorkspace(workspace.id); }}>Restore</button><span className="study-row__chevron"><span className="material-symbols-outlined study-chevron" style={{transform: isExpanded ? 'rotate(0deg)' : 'rotate(-90deg)'}}>{isExpanded ? 'expand_more' : 'chevron_right'}</span></span></div>
                    </div>
                    {isExpanded && <div className="study-children archive-children">
                      {archivedStudies.length ? archivedStudies.map(study => <div key={study.id}>
                        <div className="file-row archive-readonly"><div className="file-row__left"><span className="material-symbols-outlined">folder</span><span>{study.name}</span><span className="file-badge file-badge--default">Study</span></div><div className="file-row__meta"><span className="file-row__time">{study.lastModified}</span></div></div>
                        {datasetsByStudy[study.id] && <div className="file-row archive-readonly archive-file"><div className="file-row__left"><span className="material-symbols-outlined">dataset</span><span>{datasetsByStudy[study.id].filename}</span><span className="file-badge file-badge--default">{datasetsByStudy[study.id].rows.length} rows</span></div></div>}
                        {models.filter(model => model.studyId === study.id).map(model => <div className="file-row archive-readonly archive-file" key={model.id}><div className="file-row__left"><span className="material-symbols-outlined">account_tree</span><span>{model.name}</span><span className="file-badge file-badge--default">{model.type}</span></div><div className="file-row__meta"><span className="file-row__time">{model.lastModified}</span></div></div>)}
                      </div>) : <div className="archive-empty">No studies in this workspace.</div>}
                    </div>}
                  </div>;
                }) : <div className="empty-state" style={{padding: '32px 16px', textAlign: 'center'}}>No archived workspaces.</div>}
              </div>
            ) : <div style={{flex: '1', display: 'flex', flexDirection: 'column'}}>
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
                                    if (window.confirm(`Are you sure you want to remove study "${study.name}"?`)) {
                                      trashStudy(study.id);
                                    }
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
                              <div className="file-row file-row--muted" onClick={() => { setImportingStudyId(study.id); setDatasetToImport(studyDataset); }} onContextMenu={e => { e.preventDefault(); e.stopPropagation(); useStore.getState().openContextMenu(e.clientX, e.clientY, [{ id: 'rename', label: 'Rename Dataset', icon: 'edit', action: () => rename('Rename Dataset', studyDataset.filename, name => { setStudyDataset(study.id, { ...studyDataset, filename: name }); touchStudy(study.id); }) }, { id: 'delete', label: 'Delete Dataset', icon: 'delete', danger: true, action: () => { if (window.confirm(`Delete dataset "${studyDataset.filename}"?`)) { trashDataset(study.id); touchStudy(study.id); } } }]); }}>
                                <div className="file-row__left"><span className="material-symbols-outlined">dataset</span><span>{studyDataset.filename}</span><span className="file-badge file-badge--default">{studyDataset.rows.length} rows</span><span className="file-badge file-badge--default">Dataset</span></div>
                                <div className="file-row__meta"><span className="file-row__time">{study.lastModified}</span><span style={{width: '16px'}}></span></div>
                              </div>
                            )}
                            {studyModels.map(model => (
                              <div key={model.id} className="file-row" onClick={() => { setActiveStudy(study.id); setActiveModel(model.id); navigate('/model/' + model.id); }} onContextMenu={e => { e.preventDefault(); e.stopPropagation(); useStore.getState().openContextMenu(e.clientX, e.clientY, [{ id: 'rename', label: 'Rename Model', icon: 'edit', action: () => rename('Rename Model', model.name, name => renameModel(model.id, name)) }, { id: 'duplicate', label: 'Duplicate Model', icon: 'content_copy', action: () => duplicateModel(model.id) }, { id: 'delete', label: 'Delete Model', icon: 'delete', danger: true, action: () => { if (window.confirm(`Delete model "${model.name}"?`)) trashModel(model.id); } }]); }}>
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
            </div>}
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
