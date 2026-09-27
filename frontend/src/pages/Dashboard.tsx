import React, { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import WorkspaceModal from '../components/WorkspaceModal';
import StudyModal from '../components/StudyModal';
import InputDialog from '../components/InputDialog';
import { DataManagerModal } from '../components/DataManagerModal';
import { parseDatasetFile } from '../utils/dataset-parser';
import type { ParsedDataset } from '../utils/dataset-parser';
import { api } from '../utils/api';

const Dashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { 
    workspaces, archivedWorkspaces, activeWorkspaceId, setActiveWorkspace,
    studies, setActiveStudy, models, setActiveModel, addModel,
    datasetsByStudy, setStudyDataset, touchStudy, archiveWorkspace, restoreWorkspace, renameWorkspace,
    deleteWorkspace, deleteStudy, deleteModel, deleteDataset, requestDelete,
    renameStudy, duplicateStudy, renameModel, duplicateModel, openTab,
    isSidebarCollapsed, toggleSidebar
  } = useStore();
  
  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length > 0) {
      setActiveWorkspace(workspaces[0].id);
    }
  }, [activeWorkspaceId, workspaces, setActiveWorkspace]);

  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
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

  // Sorting state for studies
  type SortField = 'name' | 'modified' | 'created';
  type SortOrder = 'asc' | 'desc';
  const [sortField, setSortField] = useState<SortField>('modified');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [isSortMenuOpen, setIsSortMenuOpen] = useState(false);
  const sortMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (sortMenuRef.current && !sortMenuRef.current.contains(e.target as Node)) {
        setIsSortMenuOpen(false);
      }
    };
    if (isSortMenuOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
      return () => document.removeEventListener('mousedown', handleOutsideClick);
    }
  }, [isSortMenuOpen]);

  const sortedStudies = [...filteredStudies].sort((a, b) => {
    let comparison = 0;
    if (sortField === 'name') {
      comparison = a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    } else if (sortField === 'created') {
      const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
      const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
      comparison = aTime - bTime;
      if (comparison === 0) {
        comparison = a.name.localeCompare(b.name);
      }
    } else {
      // modified
      const aDate = Date.parse(a.lastModified);
      const bDate = Date.parse(b.lastModified);
      if (!isNaN(aDate) && !isNaN(bDate)) {
        comparison = aDate - bDate;
      } else {
        const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
        const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
        comparison = aTime - bTime;
      }
    }
    return sortOrder === 'asc' ? comparison : -comparison;
  });

  // Inline rename state for sidebar workspace, study, and dataset
  const [editingSidebarWsId, setEditingSidebarWsId] = useState<string | null>(null);
  const [editSidebarWsName, setEditSidebarWsName] = useState('');

  const [editingStudyId, setEditingStudyId] = useState<string | null>(null);
  const [editStudyName, setEditStudyName] = useState('');

  const [editingDatasetStudyId, setEditingDatasetStudyId] = useState<string | null>(null);
  const [editDatasetName, setEditDatasetName] = useState('');

  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [editModelName, setEditModelName] = useState('');

  const commitSidebarWsRename = (id: string) => {
    if (editSidebarWsName.trim()) {
      renameWorkspace(id, editSidebarWsName.trim());
    }
    setEditingSidebarWsId(null);
  };

  const commitStudyRename = (id: string) => {
    if (editStudyName.trim()) {
      renameStudy(id, editStudyName.trim());
    }
    setEditingStudyId(null);
  };

  const commitDatasetRename = (studyId: string, currentDataset: ParsedDataset) => {
    if (editDatasetName.trim() && editDatasetName.trim() !== currentDataset.filename) {
      const updated = { ...currentDataset, filename: editDatasetName.trim() };
      setStudyDataset(studyId, updated);
      touchStudy(studyId);
    }
    setEditingDatasetStudyId(null);
  };

  const commitModelRename = (id: string) => {
    if (editModelName.trim()) {
      renameModel(id, editModelName.trim());
    }
    setEditingModelId(null);
  };

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [datasetToImport, setDatasetToImport] = useState<ParsedDataset | null>(null);
  const [importingStudyId, setImportingStudyId] = useState<string | null>(null);

  // Inline workspace title renaming
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editWorkspaceTitle, setEditWorkspaceTitle] = useState('');
  const titleInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus();
      titleInputRef.current.select();
    }
  }, [isEditingTitle]);

  useEffect(() => {
    setIsEditingTitle(false);
  }, [activeWorkspaceId]);

  const commitTitleRename = () => {
    if (activeWorkspace && editWorkspaceTitle.trim() && editWorkspaceTitle.trim() !== activeWorkspace.name) {
      renameWorkspace(activeWorkspace.id, editWorkspaceTitle.trim());
    }
    setIsEditingTitle(false);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const parsed = await parseDatasetFile(file);
      if (importingStudyId) {
        await handleImportComplete(parsed);
        openTab({
          type: 'dataset',
          title: parsed.filename,
          studyId: importingStudyId,
          workspaceId: activeWorkspaceId,
        });
      }
    } catch (err) {
      alert("Error importing file: " + err);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleImportComplete = async (dataset: ParsedDataset) => {
    if (!importingStudyId) return;
    setStudyDataset(importingStudyId, dataset);
    touchStudy(importingStudyId);
    const study = studies.find(s => s.id === importingStudyId);
    if (study?.path) {
      try {
        const headers = dataset.variables.map(v => v.name);
        await api.saveProjectDataJson(study.path, dataset.filename, headers, dataset.rows);
      } catch (err) {
        console.warn('Failed to save dataset to project in Dashboard:', err);
      }
    }
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
                {isWorkspaceSearchOpen ? <div className="inline-search-wrap"><input autoFocus className="sidebar-inline-search" value={workspaceQuery} onChange={event => setWorkspaceQuery(event.target.value)} onBlur={() => { if (!workspaceQuery) setIsWorkspaceSearchOpen(false); }} placeholder="Filter…" />{workspaceQuery && <button className="inline-search-clear" type="button" aria-label="Clear workspace search" onMouseDown={event => event.preventDefault()} onClick={() => setWorkspaceQuery('')}>×</button>}</div> : <span className="sidebar-header__label">Workspaces</span>}
                <div className="sidebar-header__actions">
                  <button className={`icon-btn icon-btn--sm ${isWorkspaceSearchOpen ? 'active' : ''}`} title="Search workspaces" type="button" onClick={() => {
                    if (isSidebarCollapsed) {
                      toggleSidebar();
                      setTimeout(() => setIsWorkspaceSearchOpen(true), 150);
                    } else {
                      setIsWorkspaceSearchOpen(open => !open);
                      if (isWorkspaceSearchOpen) setWorkspaceQuery('');
                    }
                  }}>
                    <span className="material-symbols-outlined">search</span>
                  </button>
                  <button className="sidebar-create-folder-btn" title="Create Workspace" type="button" onClick={() => setIsWorkspaceModalOpen(true)}>
                    <svg fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
                      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"></path>
                      <line x1="12" x2="12" y1="10" y2="16"></line>
                      <line x1="9" x2="15" y1="13" y2="13"></line>
                    </svg>
                  </button>
                  <button className="icon-btn icon-btn--sm" id="sidebar-collapse-btn" title={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} type="button" onClick={toggleSidebar}>
                    <span className="material-symbols-outlined">left_panel_close</span>
                  </button>
                </div>
              </div>

              <div id="sidebar-ws-list" style={{display: 'flex', flexDirection: 'column', gap: '2px'}}>
                {filteredWorkspaces.map(ws => (
                  <div 
                    key={ws.id} 
                    className={`sidebar-item ${ws.id === activeWorkspaceId ? 'active' : ''}`}
                    onClick={() => {
                      if (editingSidebarWsId !== ws.id) {
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
                            setEditingSidebarWsId(ws.id);
                            setEditSidebarWsName(ws.name);
                          }
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
                              onConfirm: async () => {
                                if (ws.path) {
                                  try {
                                    await api.deleteWorkspace(ws.path);
                                  } catch (e) {
                                    console.warn('Failed to delete workspace on disk:', e);
                                  }
                                }
                                deleteWorkspace(ws.id);
                              },
                            });
                          } 
                        }
                      ]);
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <span className="sidebar-item__left" style={{ width: '100%', overflow: 'hidden' }}>
                      <span className="material-symbols-outlined">folder</span>
                      {editingSidebarWsId === ws.id ? (
                        <input
                          autoFocus
                          type="text"
                          className="inline-seamless-rename-input"
                          value={editSidebarWsName}
                          size={Math.max(editSidebarWsName.length, 1)}
                          onChange={(e) => setEditSidebarWsName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitSidebarWsRename(ws.id);
                            else if (e.key === 'Escape') setEditingSidebarWsId(null);
                          }}
                          onBlur={() => commitSidebarWsRename(ws.id)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      ) : (
                        <span>{ws.name}</span>
                      )}
                    </span>
                  </div>
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
            <button className="sidebar-item" type="button" data-action="docs" onClick={() => openTab({ type: 'docs', title: 'Documentation' })}>
              <span className="sidebar-item__left">
                <span className="material-symbols-outlined">menu_book</span>
                <span>Documentation</span>
              </span>
            </button>
            <button className="sidebar-item" type="button" data-action="samples" onClick={() => openTab({ type: 'samples', title: 'Sample Projects' })}>
              <span className="sidebar-item__left">
                <span className="material-symbols-outlined">science</span>
                <span>Sample Projects</span>
              </span>
            </button>
            <button className="sidebar-item" type="button" data-action="feedback" onClick={() => openTab({ type: 'feedback', title: 'Feedback & Reports' })}>
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
                {isEditingTitle ? (
                  <input
                    ref={titleInputRef}
                    type="text"
                    className="ws-title-rename-input"
                    value={editWorkspaceTitle}
                    size={Math.max(editWorkspaceTitle.length, 1)}
                    onChange={(e) => setEditWorkspaceTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        commitTitleRename();
                      } else if (e.key === 'Escape') {
                        e.preventDefault();
                        setIsEditingTitle(false);
                      }
                    }}
                    onBlur={commitTitleRename}
                  />
                ) : (
                  <h1
                    className="ws-title-editable"
                    onDoubleClick={() => {
                      if (activeWorkspace) {
                        setEditWorkspaceTitle(activeWorkspace.name);
                        setIsEditingTitle(true);
                      }
                    }}
                    title="Double-click to rename workspace"
                  >
                    {activeWorkspace?.name || 'Workspace'}
                  </h1>
                )}
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
                <div style={{display: 'flex', alignItems: 'center', gap: '16px'}}>
                  {/* Inline Sort Control */}
                  <div style={{ position: 'relative' }} ref={sortMenuRef}>
                    <button
                      type="button"
                      onClick={() => setIsSortMenuOpen((prev) => !prev)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: 0,
                        border: 'none',
                        background: 'transparent',
                        color: isSortMenuOpen ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 'var(--text-xs)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        cursor: 'pointer',
                        transition: 'color 0.15s ease',
                      }}
                      title="Sort studies"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '14px', color: 'currentColor' }}>
                        sort
                      </span>
                      <span>
                        {sortField === 'name' ? 'Name' : sortField === 'created' ? 'Date Created' : 'Date Modified'}
                      </span>
                      <span className="material-symbols-outlined" style={{ fontSize: '14px', color: 'currentColor' }}>
                        {sortOrder === 'asc' ? 'arrow_upward' : 'arrow_downward'}
                      </span>
                    </button>

                    {isSortMenuOpen && (
                      <div
                        style={{
                          position: 'absolute',
                          top: 'calc(100% + 8px)',
                          right: 0,
                          zIndex: 1000,
                          backgroundColor: 'var(--color-bg-base)',
                          border: '1px solid var(--color-border-subtle)',
                          borderRadius: 'var(--radius-md, 6px)',
                          boxShadow: '0 4px 16px rgba(0,0,0,0.1), 0 1px 3px rgba(0,0,0,0.05)',
                          minWidth: '160px',
                          padding: '4px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '2px',
                        }}
                      >
                        {[
                          { field: 'modified' as const, label: 'Date Modified' },
                          { field: 'created' as const, label: 'Date Created' },
                          { field: 'name' as const, label: 'Name' },
                        ].map((opt) => {
                          const isSelected = sortField === opt.field;
                          return (
                            <button
                              key={opt.field}
                              type="button"
                              onClick={() => {
                                if (isSelected) {
                                  setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
                                } else {
                                  setSortField(opt.field);
                                  setSortOrder(opt.field === 'name' ? 'asc' : 'desc');
                                }
                              }}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '6px 8px',
                                borderRadius: 'var(--radius-sm, 4px)',
                                border: 'none',
                                background: isSelected ? 'var(--color-accent-subtle)' : 'transparent',
                                color: isSelected ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                                fontFamily: 'var(--font-mono)',
                                fontSize: 'var(--text-xs)',
                                textTransform: 'uppercase',
                                letterSpacing: '0.05em',
                                cursor: 'pointer',
                                textAlign: 'left',
                                width: '100%',
                                transition: 'background-color 0.15s ease, color 0.15s ease',
                              }}
                            >
                              <span>{opt.label}</span>
                              {isSelected && (
                                <span className="material-symbols-outlined" style={{ fontSize: '13px', color: 'var(--color-accent)' }}>
                                  {sortOrder === 'asc' ? 'arrow_upward' : 'arrow_downward'}
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>

                </div>
              </div>

              <div className="studies-list" id="studies-container">
                {sortedStudies.length === 0 && (
                  <div className="empty-state animate-fade-in" style={{ padding: '32px 16px', textAlign: 'center' }}>
                    <div style={{fontSize: 'var(--text-md)', color: studyQuery ? 'var(--color-danger)' : 'var(--color-text-secondary)'}}>{studyQuery ? 'No studies found' : 'Create a new study to get started.'}</div>
                  </div>
                )}
                
                {sortedStudies.map(study => {
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
                                { 
                                  id: 'rename', 
                                  label: 'Rename Study', 
                                  icon: 'edit', 
                                  action: () => {
                                    setEditingStudyId(study.id);
                                    setEditStudyName(study.name);
                                  } 
                                },
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
                          {editingStudyId === study.id ? (
                            <input
                              autoFocus
                              type="text"
                              className="inline-seamless-rename-input"
                              value={editStudyName}
                              size={Math.max(editStudyName.length, 1)}
                              onChange={(e) => setEditStudyName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') commitStudyRename(study.id);
                                else if (e.key === 'Escape') setEditingStudyId(null);
                              }}
                              onBlur={() => commitStudyRename(study.id)}
                              onClick={(e) => e.stopPropagation()}
                            />
                          ) : (
                            <span 
                              className="study-row__name" 
                              style={isEmpty ? {color: 'var(--color-text-secondary)', fontWeight: 400} : {}}
                            >
                              {study.name}
                            </span>
                          )}
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
                            <span className="material-symbols-outlined study-chevron" style={{transform: isExpanded || isEmpty ? 'rotate(90deg)' : 'rotate(90deg)'}}>
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
<div
  className="file-row file-row--muted"
  onClick={() => {
    setActiveStudy(study.id);
    openTab({
      type: 'dataset',
      title: studyDataset.filename,
      studyId: study.id,
      workspaceId: activeWorkspaceId,
    });
  }}
  onContextMenu={e => {
    e.preventDefault();
    e.stopPropagation();

    useStore.getState().openContextMenu(
      e.clientX,
      e.clientY,
      [
        {
          id: 'open-tab',
          label: 'Open in Tab',
          icon: 'tab',
          action: () => {
            setActiveStudy(study.id);
            openTab({
              type: 'dataset',
              title: studyDataset.filename,
              studyId: study.id,
              workspaceId: activeWorkspaceId,
            });
          }
        },
        {
          id: 'quick-edit',
          label: 'Edit Settings...',
          icon: 'tune',
          action: () => {
            setImportingStudyId(study.id);
            setDatasetToImport(studyDataset);
          }
        },
        {
          id: 'rename',
          label: 'Rename Dataset',
          icon: 'edit',
          action: () => {
            setEditingDatasetStudyId(study.id);
            setEditDatasetName(studyDataset.filename);
          }
        },
        {
          id: 'delete',
          label: 'Delete Dataset',
          icon: 'delete',
          danger: true,
          action: () => {
            requestDelete({
              title: 'Delete Dataset',
              itemName: studyDataset.filename,
              message:
                'Are you sure? This dataset will be permanently deleted and cannot be recovered.',
              onConfirm: () => {
                deleteDataset(study.id);
                touchStudy(study.id);

                if (study.path) {
                  api.deleteProjectData(study.path).catch(console.warn);
                }
              }
            });
          }
        }
      ]
    );
  }}
>
                                <div className="file-row__left">
                                  <span className="material-symbols-outlined">dataset</span>
                                  {editingDatasetStudyId === study.id ? (
                                    <input
                                      autoFocus
                                      type="text"
                                      className="inline-seamless-rename-input"
                                      value={editDatasetName}
                                      size={Math.max(editDatasetName.length, 1)}
                                      onChange={(e) => setEditDatasetName(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') commitDatasetRename(study.id, studyDataset);
                                        else if (e.key === 'Escape') setEditingDatasetStudyId(null);
                                      }}
                                      onBlur={() => commitDatasetRename(study.id, studyDataset)}
                                      onClick={(e) => e.stopPropagation()}
                                    />
                                  ) : (
                                    <span>{studyDataset.filename}</span>
                                  )}
                                  <span className="file-badge file-badge--default">{studyDataset.rows.length} rows</span>
                                  <span className="file-badge file-badge--default">Dataset</span>
                                </div>
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
                              }} onContextMenu={e => { e.preventDefault(); e.stopPropagation(); useStore.getState().openContextMenu(e.clientX, e.clientY, [{ id: 'rename', label: 'Rename Model', icon: 'edit', action: () => { setEditingModelId(model.id); setEditModelName(model.name); } }, { id: 'duplicate', label: 'Duplicate Model', icon: 'content_copy', action: () => duplicateModel(model.id) }, { id: 'delete', label: 'Delete Model', icon: 'delete', danger: true, action: () => { requestDelete({ title: 'Delete Model', itemName: model.name, message: 'Are you sure? This model will be permanently deleted and cannot be recovered.', onConfirm: () => deleteModel(model.id) }); } }]); }}>
                                <div className="file-row__left">
                                  <span className="material-symbols-outlined">{model.type === 'Dataset' ? 'dataset' : 'account_tree'}</span>
                                  {editingModelId === model.id ? (
                                    <input
                                      autoFocus
                                      type="text"
                                      className="inline-seamless-rename-input"
                                      value={editModelName}
                                      size={Math.max(editModelName.length, 1)}
                                      onChange={(e) => setEditModelName(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') commitModelRename(model.id);
                                        else if (e.key === 'Escape') setEditingModelId(null);
                                      }}
                                      onBlur={() => commitModelRename(model.id)}
                                      onClick={(e) => e.stopPropagation()}
                                    />
                                  ) : (
                                    <span>{model.name}</span>
                                  )}
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
