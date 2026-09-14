import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { initModelCanvas } from '../utils/model-canvas';
import { DataManagerModal } from '../components/DataManagerModal';
import type { ParsedDataset } from '../utils/dataset-parser';
import { parseDatasetFile, processData } from '../utils/dataset-parser';
import { api } from '../utils/api';
import { Upload } from 'lucide-react';
import '../model-canvas.css';
import '../results.css';

const ModelEditor = () => {
  const navigate = useNavigate();
  const { workspaces, activeWorkspaceId, studies, activeStudyId, activeModelId, models, datasetsByStudy, setStudyDataset, touchStudy } = useStore();
  
  const activeWorkspace = workspaces.find(w => w.id === activeWorkspaceId);
  const activeStudy = studies.find(s => s.id === activeStudyId);
  const activeModel = models.find(model => model.id === activeModelId);

  const [datasetToImport, setDatasetToImport] = useState<ParsedDataset | null>(null);
  const [activeDataset, setActiveDataset] = useState<ParsedDataset | null>(() => activeStudyId ? datasetsByStudy[activeStudyId] ?? null : null);
  const [isImporting, setIsImporting] = useState(false);
  const [variableFilter, setVariableFilter] = useState('');
  const [areCategoriesCollapsed, setAreCategoriesCollapsed] = useState(false);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fixedFills = ['#334155', '#ffffff'];
  const fixedBorders = ['transparent', '#1e293b'];
  const fixedTexts = ['#ffffff', '#1e293b'];

  const [recentFills, setRecentFills] = useState<string[]>(['#fef08a']);
  const [recentBorders, setRecentBorders] = useState<string[]>(['#ca8a04']);
  const [recentTextColors, setRecentTextColors] = useState<string[]>(['#ca8a04']);
  
  const [activeFill, setActiveFill] = useState<string>('#ffffff');
  const [activeBorder, setActiveBorder] = useState<string>('#cbd5e1');
  const [activeText, setActiveText] = useState<string>('#1e293b');

  useEffect(() => {
    if (activeStudyId && datasetsByStudy[activeStudyId]) {
      setActiveDataset(datasetsByStudy[activeStudyId]);
    } else if (activeStudyId && activeStudy?.path) {
      // Try to load dataset from project file if not in store
      api.loadProjectData(activeStudy.path).then((dataRes) => {
        if (dataRes && Array.isArray(dataRes.columns) && Array.isArray(dataRes.rows) && dataRes.rows.length > 0) {
          const datasetName = dataRes.dataset_name || `${activeStudy.name} Data`;
          const parsed = processData(datasetName, dataRes.columns, dataRes.rows);
          setStudyDataset(activeStudyId, parsed);
          setActiveDataset(parsed);
        } else {
          setActiveDataset(null);
        }
      }).catch(() => {
        setActiveDataset(null);
      });
    } else {
      setActiveDataset(null);
    }
  }, [activeStudyId, datasetsByStudy, activeStudy?.path, activeStudy?.name, setStudyDataset]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setIsImporting(true);
      const parsed = await parseDatasetFile(file);
      setDatasetToImport(parsed);
    } catch (err) {
      alert("Error importing file: " + err);
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleImportComplete = async (dataset: ParsedDataset) => {
    setActiveDataset(dataset);
    if (activeStudyId) {
      setStudyDataset(activeStudyId, dataset);
      touchStudy(activeStudyId);
      if (activeStudy?.path) {
        try {
          const headers = dataset.variables.map(v => v.name);
          await api.saveProjectDataJson(activeStudy.path, dataset.filename, headers, dataset.rows);
        } catch (err) {
          console.warn('Failed to save dataset to project in ModelEditor:', err);
        }
      }
    }
    setDatasetToImport(null);
  };

  const visibleVariables = (activeDataset?.variables ?? []).filter(variable =>
    variable?.selected && (!variableFilter || String(variable.name ?? '').toLocaleLowerCase().includes(variableFilter.toLocaleLowerCase()))
  );
  const categories = Array.from(new Set(visibleVariables.map(variable => String(variable.category ?? 'General'))));

  const toggleCategory = (category: string) => {
    setCollapsedCategories(current => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  const handleVariableDragStart = (event: React.DragEvent<HTMLDivElement>, variableName: string) => {
    event.dataTransfer.setData('text/plain', variableName);
    event.dataTransfer.effectAllowed = 'copy';
  };

  const handleCanvasDrop = (event: React.DragEvent<SVGSVGElement>) => {
    event.preventDefault();
    const variableName = event.dataTransfer.getData('text/plain');
    (window as any).dropModelVariable?.(variableName, event.clientX, event.clientY);
  };

  useEffect(() => {
    // Add global sync method for color pickers
    (window as any).syncColorPickers = (fill: string, border: string, text: string) => {
      if (fill) setActiveFill(fill);
      if (border) setActiveBorder(border);
      if (text) setActiveText(text);
    };

    // Add a tiny delay to ensure DOM is ready
    const timer = setTimeout(() => {
      initModelCanvas();
      // Load results script if it exists
      import('../utils/results.js').then((m) => {
        if (m.initResults) m.initResults();
      }).catch(() => {});

      // Add view toggle logic
      const calculateBtn = document.getElementById('calculate-btn');
      const viewSlider = document.getElementById('main-view-slider');
      const viewModel = document.getElementById('view-model');
      const viewResults = document.getElementById('view-results');
      const sliderBtns = viewSlider?.querySelectorAll('.view-slider__btn');
      const sliderBg = viewSlider?.querySelector('.view-slider__bg');

      let currentView = 'model';

      function switchView(view: string) {
        if (!viewModel || !viewResults || !sliderBg || !sliderBtns) return;
        if (view === 'model') {
          (viewModel as HTMLElement).style.display = 'block';
          (viewResults as HTMLElement).style.display = 'none';
          (sliderBg as HTMLElement).style.transform = 'translateX(0)';
          sliderBtns[0].classList.add('active');
          sliderBtns[1].classList.remove('active');
        } else {
          (viewModel as HTMLElement).style.display = 'none';
          (viewResults as HTMLElement).style.display = 'block';
          (sliderBg as HTMLElement).style.transform = 'translateX(100%)';
          sliderBtns[1].classList.add('active');
          sliderBtns[0].classList.remove('active');
        }
        currentView = view;
      }

      if (calculateBtn && viewSlider) {
        calculateBtn.addEventListener('click', () => {
          calculateBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.59-9.21l5.67-1.35"/></svg>
            Recalculate
          `;
          (viewSlider as HTMLElement).style.display = 'flex';
          switchView('results');
        });
      }

      if (sliderBtns) {
        sliderBtns.forEach(btn => {
          btn.addEventListener('click', (e) => {
            const target = e.currentTarget as HTMLElement | null;
            switchView(target?.dataset?.view || 'model');
          });
        });
      }
    }, 100);

    const handleColorPickerClosed = (e: any) => {
      const { id, color } = e.detail;
      if (id === 'picker-fill') {
        setActiveFill(color);
        setRecentFills(prev => {
          if (['#334155', '#ffffff'].includes(color)) return prev;
          return [...prev.filter(c => c !== color), color].slice(-3);
        });
      } else if (id === 'picker-border') {
        setActiveBorder(color);
        setRecentBorders(prev => {
          if (['transparent', '#1e293b'].includes(color)) return prev;
          return [...prev.filter(c => c !== color), color].slice(-3);
        });
      } else if (id === 'picker-text') {
        setActiveText(color);
        setRecentTextColors(prev => {
          if (['#ffffff', '#1e293b'].includes(color)) return prev;
          return [...prev.filter(c => c !== color), color].slice(-1);
        });
      }
    };
    
    document.addEventListener('color-picker-closed', handleColorPickerClosed);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('color-picker-closed', handleColorPickerClosed);
    };
  }, []);

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>

  {/* ═══ TITLE BAR ═══ */}
  <header className="titlebar window-drag">
    <div className="titlebar__left no-drag">
      <div className="titlebar__traffic-light-space" aria-hidden="true"></div>
      <div
        className="brand"
        onClick={() => navigate('/')}
        role="button"
        tabIndex={0}
        title="Go to Getting Started"
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') navigate('/'); }}
      >
        <svg className="brand__logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width={48} height={48} rx={10} fill="#6B4EE6" />
          <circle cx={16} cy={16} r={4} fill="#FFFFFF" />
          <circle cx={32} cy={18} r={4} fill="#C7D2FE" />
          <circle cx={20} cy={32} r={5} fill="#EEF2FF" />
          <circle cx={34} cy={32} r="3.5" fill="#A5B4FC" />
          <path d="M16 16L32 18M16 16L20 32M20 32L34 32M32 18L34 32" stroke="#FFFFFF" strokeWidth={2} strokeLinecap="round" strokeOpacity="0.85" />
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
      <span className="v-divider" />
      <div className="user-badge" role="button" tabIndex={0}>
        <div className="user-badge__avatar">
          <span>MV</span>
          <span className="user-badge__status" />
        </div>
        <span className="user-badge__name">M. Vance</span>
      </div>
    </div>
  </header>
  {/* ═══ SUB-HEADER / CONTROL BAR ═══ */}
  <div className="subheader">
    <div className="subheader__breadcrumb">
      <span className="subheader__breadcrumb-link" id="current-model-workspace" onClick={() => navigate('/workspace')}>{activeWorkspace?.name || 'Active_Workspace'}</span>
      <span className="subheader__breadcrumb-sep">/</span>
      <span className="subheader__breadcrumb-link" id="current-model-study" onClick={() => navigate('/workspace')}>{activeStudy?.name || 'Active_Study'}</span>
      <span className="subheader__breadcrumb-sep">/</span>
      <span className="subheader__breadcrumb-link" style={{color: 'var(--color-accent)'}}>
        {activeModel ? `${activeModel.name}.splsm` : 'Untitled model.splsm'}
      </span>
    </div>
    <div className="subheader__actions">
      {/* Segmented Control for Views (Hidden initially) */}
      <div className="view-slider" id="main-view-slider" style={{display: 'none'}}>
        <div className="view-slider__bg" />
        <button className="view-slider__btn active" data-view="model">
          <span className="material-symbols-outlined">polyline</span>
          Model
        </button>
        <button className="view-slider__btn" data-view="results">
          <span className="material-symbols-outlined">table_chart</span>
          Results
        </button>
      </div>
      <button className="subheader__btn subheader__btn--primary" id="calculate-btn" type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polygon points="5 3 19 12 5 21 5 3" /></svg>
        Calculate
      </button>
      <div className="subheader__divider" />
      <button className="subheader__btn subheader__btn--ghost" type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></svg>
        Save
      </button>
      <button className="subheader__btn subheader__btn--ghost" type="button">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1={12} y1={15} x2={12} y2={3} /></svg>
        Export
      </button>
    </div>
  </div>
  {/* ═══ APP BODY ═══ */}
  <div id="view-model" className="view-panel">
    <div className="app-body">
      {/* ─── Variable Sidebar (Left) ─── */}
      <aside className="var-sidebar" id="var-sidebar">
        <div className="var-sidebar__search">
          <div className="var-sidebar__search-inner">
            <svg className="var-sidebar__search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={11} cy={11} r={8} /><line x1={21} y1={21} x2="16.65" y2="16.65" /></svg>
            <input type="text" className="var-sidebar__search-input" value={variableFilter} onChange={event => setVariableFilter(event.currentTarget.value)} placeholder="Filter variables... (⌘F)" />
          </div>
        </div>
        
        {activeDataset ? (
          <div className="var-sidebar__header">
            <span className="var-sidebar__header-label" title={activeDataset.filename}>{activeDataset.filename}</span>
            <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
              <span className="var-sidebar__count">{activeDataset.variables.filter(v => v?.selected).length} vars</span>
              <button type="button" className="var-sidebar__collapse-all" onClick={() => setAreCategoriesCollapsed(current => !current)}>
                {areCategoriesCollapsed ? 'Expand' : 'Collapse'}
              </button>
            </div>
          </div>
        ) : (
          <div className="var-sidebar__header" style={{ justifyContent: 'space-between' }}>
            <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
              <span className="var-sidebar__header-label">Dataset Variables</span>
              <span className="var-sidebar__count">0</span>
            </div>
            <span style={{ fontSize: '10px', color: '#d97706', backgroundColor: '#fef3c7', border: '1px solid #fde68a', padding: '1px 6px', borderRadius: '4px', fontWeight: 500 }}>
              Unlinked
            </span>
          </div>
        )}

        {activeDataset ? (
          <div className="var-sidebar__list" id="var-list">
            {categories.map(cat => {
              const varsInCat = visibleVariables.filter(v => String(v.category ?? 'General') === cat);
              if (varsInCat.length === 0) return null;
              return (
                <div className="var-cat" key={cat}>
                  <button type="button" className="var-cat__header" onClick={() => toggleCategory(cat)}>
                    <div className="var-cat__header-left">
                      <svg className={`cat-chevron ${areCategoriesCollapsed || collapsedCategories.has(cat) ? 'rotated' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polyline points="6 9 12 15 18 9" /></svg>
                      <span className="var-cat__name">{cat}</span>
                    </div>
                    <span className="var-cat__count">{varsInCat.length}</span>
                  </button>
                  <div className={`var-items ${areCategoriesCollapsed || collapsedCategories.has(cat) ? 'hidden' : ''}`}>
                    {varsInCat.map(v => (
                      <div className="var-item" key={v.name} data-variable-name={String(v.name ?? '')} draggable onDragStart={event => handleVariableDragStart(event, String(v.name ?? ''))}>
                        <span className="var-item__name">{v.name}</span>
                        <span className="var-item__type">{String(v.scaleType ?? 'Unknown').slice(0, 3).toUpperCase()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '12px', overflowY: 'auto' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div 
                style={{ border: '2px dashed #cbd5e1', backgroundColor: '#f8fafc', borderRadius: '12px', padding: '16px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', cursor: 'pointer', transition: 'border-color 0.2s, background-color 0.2s' }}
                onClick={() => fileInputRef.current?.click()}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#818cf8'; e.currentTarget.style.backgroundColor = '#f1f5f9'; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.backgroundColor = '#f8fafc'; }}
              >
                <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: '#e0e7ff', border: '1px solid #c7d2fe', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4f46e5' }}>
                  <svg style={{ width: '20px', height: '20px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8"></path>
                  </svg>
                </div>
                <div>
                  <p style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b', margin: '0 0 4px 0' }}>Drop dataset here</p>
                  <p style={{ fontSize: '10px', color: '#94a3b8', margin: 0, lineHeight: 1.4 }}>CSV, TXT, or Excel (.xlsx) data matrix to populate variables</p>
                </div>
                <button 
                  style={{ marginTop: '4px', height: '28px', padding: '0 12px', borderRadius: '4px', fontSize: '12px', fontWeight: 500, color: 'white', backgroundColor: '#4f46e5', border: 'none', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}
                  disabled={isImporting}
                  onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                >
                  <svg style={{ width: '14px', height: '14px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path></svg>
                  <span>{isImporting ? 'Parsing...' : 'Select Dataset File'}</span>
                </button>
              </div>
            </div>
            <div style={{ textAlign: 'center', padding: '8px 0', borderTop: '1px solid #f1f5f9', marginTop: '12px' }}>
              <span style={{ fontSize: '10px', color: '#94a3b8' }}>Variables will appear here once loaded</span>
            </div>
            <input 
              type="file" 
              accept=".csv,.txt,.xlsx,.xls,.sav"
              ref={fileInputRef}
              onChange={handleFileUpload}
              style={{ display: 'none' }}
            />
          </div>
        )}
      </aside>
      {/* ─── Center Canvas Area ─── */}
      <main className="canvas-area">
        {/* Toolbar Pill */}
        <div className="canvas-toolbar">
          <div className="tb-btn active" title="Select (V)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z" /><path d="M13 13l6 6" /></svg></div>
          <div className="tb-btn" title="Latent variable (O)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={12} r={8} /></svg></div>
          <div className="tb-btn" title="Path Connector (P)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><line x1={5} y1={12} x2={19} y2={12} /><polyline points="12 5 19 12 12 19" /></svg></div>
          <div className="tb-btn" title="Moderation Effect (M)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={12} r={10} /><line x1={12} y1={8} x2={12} y2={16} /><line x1={8} y1={12} x2={16} y2={12} /></svg></div>
          <div className="tb-btn" title="Quadratic Effect (Q)"><span className="tb-btn--text">x²</span></div>
          <div className="tb-btn" title="Gaussian Copula"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M4 22h14a2 2 0 0 0 2-2V7.5L14.5 2H6a2 2 0 0 0-2 2v4" /><polyline points="14 2 14 8 20 8" /><path d="M2 15h10" /><path d="M6 11l-4 4 4 4" /></svg></div>
          <div className="tb-btn" title="Text Note (T)" data-action="add-text-note"><span className="tb-btn--text">T</span></div>
          <div className="tb-divider" />
          <div className="tb-btn" title="Auto-Align Model"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><rect x={4} y={4} width={6} height={6} rx={1} /><rect x={14} y={14} width={6} height={6} rx={1} /><line x1={10} y1={7} x2={17} y2={7} /><line x1={17} y1={7} x2={17} y2={14} /></svg></div>
          <div id="node-formatting-tools" style={{display: 'flex', gap: '4px'}}>
          <div className="tb-dropdown-container">
            <button className="tb-dropdown-btn" type="button" title="Alignment" id="btn-align">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><line x1={21} y1={6} x2={3} y2={6} /><line x1={15} y1={12} x2={3} y2={12} /><line x1={17} y1={18} x2={3} y2={18} /></svg>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div className="tb-dropdown-menu" id="menu-align">
              <div className="tb-dropdown-item" data-action="align-top"><span className="material-symbols-outlined">align_vertical_top</span> Align Top</div>
              <div className="tb-dropdown-item" data-action="align-bottom"><span className="material-symbols-outlined">align_vertical_bottom</span> Align Bottom</div>
              <div className="tb-dropdown-item" data-action="align-left"><span className="material-symbols-outlined">align_horizontal_left</span> Align Left</div>
              <div className="tb-dropdown-item" data-action="align-right"><span className="material-symbols-outlined">align_horizontal_right</span> Align Right</div>
            </div>
          </div>
          <div className="tb-dropdown-container">
            <button className="tb-dropdown-btn" type="button" title="Style" id="btn-style">
              <div className="tb-shape-preview" />
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div className="tb-dropdown-menu" id="menu-style">
              <div className="tb-dropdown-item" data-action="shape-circle"><span className="material-symbols-outlined">radio_button_unchecked</span> Circle</div>
              <div className="tb-dropdown-item" data-action="shape-rect"><span className="material-symbols-outlined">crop_square</span> Rectangle</div>
              <div className="tb-dropdown-item" data-action="shape-hex"><span className="material-symbols-outlined">hexagon</span> Hexagon</div>
              <div className="tb-dropdown-item" data-action="shape-oct"><span className="material-symbols-outlined">stop_circle</span> Octagon</div>
            </div>
          </div>
          <div className="tb-dropdown-container">
            <button className="tb-dropdown-btn" type="button" title="Color &amp; Stroke Styling" id="btn-colors">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"></circle><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"></circle><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"></circle><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"></circle><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M12 2C6.477 2 2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.878v-1.785a2.5 2.5 0 012.5-2.5h1.156a4.5 4.5 0 004.5-4.5c0-.62-.126-1.213-.355-1.752A10.007 10.007 0 0012 2z"></path></svg>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 14, height: 14}}><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div className="tb-dropdown-menu" id="menu-colors" style={{width: '240px', padding: '12px'}}>
              <div style={{marginBottom: '12px'}}>
                <div style={{fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-hint)', marginBottom: '8px'}}>Fill Color</div>
              <div className="tb-divider" style={{width: '100%', height: '1px', margin: '8px 0'}}></div>
                <div style={{fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-hint)', marginBottom: '8px'}}>Fill Color</div>
                <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap'}}>
                  {[...fixedFills, ...recentFills].map((color, i) => (
                    <button key={'fill'+i} type="button" style={{width: '24px', height: '24px', borderRadius: '50%', background: color === 'transparent' ? 'url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVQIW2NkYGD4z8DAwMgAI0AMDA4YAQc0D+oAAAAASUVORK5CYII=)' : color, border: activeFill === color ? '2px solid #4f46e5' : '1px solid rgba(0,0,0,0.1)', boxShadow: activeFill === color ? '0 0 0 2px rgba(79, 70, 229, 0.2)' : 'none'}} onClick={() => { 
                      document.dispatchEvent(new CustomEvent('color-picker-input', { detail: { id: 'picker-fill', color } }));
                      document.dispatchEvent(new CustomEvent('color-picker-closed', { detail: { id: 'picker-fill', color } }));
                      setActiveFill(color);
                    }} title={color}></button>
                  ))}
                  <button type="button" style={{width: '24px', height: '24px', borderRadius: '50%', background: '#f4f4f5', border: '1px dashed rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(0,0,0,0.5)', position: 'relative'}} title="Custom Color">
                    <span style={{fontSize: '14px', fontWeight: 500}}>+</span>
                    <input type="color" id="picker-fill" title="Fill Color" defaultValue="#f8fafc" style={{position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer'}} 
                      onInput={(e: any) => document.dispatchEvent(new CustomEvent('color-picker-input', { detail: { id: 'picker-fill', color: e.target.value } }))}
                      onChange={(e: any) => document.dispatchEvent(new CustomEvent('color-picker-closed', { detail: { id: 'picker-fill', color: e.target.value } }))}
                    />
                  </button>
                </div>
              </div>

              <div className="tb-divider" style={{width: '100%', height: '1px', margin: '8px 0'}}></div>

              <div>
                <div style={{fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-hint)', marginBottom: '8px'}}>Border Color</div>
                <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap'}}>
                  {[...fixedBorders, ...recentBorders].map((color, i) => (
                    <button key={'border'+i} type="button" style={{width: '24px', height: '24px', borderRadius: '50%', background: color === 'transparent' ? 'url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVQIW2NkYGD4z8DAwMgAI0AMDA4YAQc0D+oAAAAASUVORK5CYII=)' : color, border: activeBorder === color ? '2px solid #4f46e5' : '1px solid rgba(0,0,0,0.1)', boxShadow: activeBorder === color ? '0 0 0 2px rgba(79, 70, 229, 0.2)' : 'none'}} onClick={() => { 
                      document.dispatchEvent(new CustomEvent('color-picker-input', { detail: { id: 'picker-border', color } }));
                      document.dispatchEvent(new CustomEvent('color-picker-closed', { detail: { id: 'picker-border', color } }));
                      setActiveBorder(color);
                    }} title={color}></button>
                  ))}
                  <button type="button" style={{width: '24px', height: '24px', borderRadius: '50%', background: '#f4f4f5', border: '1px dashed rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(0,0,0,0.5)', position: 'relative'}} title="Custom Color">
                    <span style={{fontSize: '14px', fontWeight: 500}}>+</span>
                    <input type="color" id="picker-border" title="Border Color" defaultValue="#cbd5e1" style={{position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer'}}
                      onInput={(e: any) => document.dispatchEvent(new CustomEvent('color-picker-input', { detail: { id: 'picker-border', color: e.target.value } }))}
                      onChange={(e: any) => document.dispatchEvent(new CustomEvent('color-picker-closed', { detail: { id: 'picker-border', color: e.target.value } }))}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>
          
          <div className="tb-dropdown-container">
            <button className="tb-dropdown-btn" type="button" title="Typography Settings" id="btn-text">
              <span style={{fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)'}}>Aa</span>
              <span className="tb-font-size-label" style={{fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--color-text-hint)', marginLeft: '2px'}}>14</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 14, height: 14, marginLeft: '2px'}}><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div className="tb-dropdown-menu" id="menu-text" style={{width: '240px', padding: '12px'}}>
              <div style={{marginBottom: '12px'}}>
                <div style={{fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-hint)', marginBottom: '8px'}}>Font Family</div>
                <select id="input-font-family" style={{width: '100%', background: '#f8fafc', border: '1px solid rgba(0,0,0,0.06)', borderRadius: '4px', padding: '4px 8px', fontSize: '11px', color: '#334155', outline: 'none'}}>
                  <option value="Inter">Inter (Sans)</option>
                  <option value="JetBrains Mono">JetBrains Mono</option>
                  <option value="Roboto">Roboto</option>
                  <option value="system-ui">System Default</option>
                </select>
              </div>

              <div className="tb-divider" style={{width: '100%', height: '1px', margin: '6px 0'}}></div>
              
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px'}}>
                <span style={{fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--color-text-hint)'}}>Font Size</span>
                <div className="tb-font-size" style={{background: 'rgba(0,0,0,0.03)', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.06)', padding: '2px', display: 'flex', alignItems: 'center'}}>
                  <button className="tb-font-btn" data-action="font-dec" style={{width: '22px', height: '22px', border: 'none', background: 'transparent', cursor: 'pointer', borderRadius: '2px'}}>−</button>
                  <input type="number" className="tb-font-input" id="input-font-size" defaultValue={14} style={{display: 'none'}} />
                  <span className="tb-font-size-label" style={{fontFamily: 'var(--font-mono)', fontSize: '12px', width: '32px', textAlign: 'center', fontWeight: 600}}>14px</span>
                  <button className="tb-font-btn" data-action="font-inc" style={{width: '22px', height: '22px', border: 'none', background: 'transparent', cursor: 'pointer', borderRadius: '2px'}}>+</button>
                </div>
              </div>
              <div className="tb-divider" style={{width: '100%', height: '1px', margin: '6px 0'}}></div>
              
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px'}}>
                <div style={{display: 'flex', background: 'rgba(0,0,0,0.03)', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.06)', padding: '2px'}}>
                  <button className="tb-font-btn" data-action="text-bold" style={{width: '26px', height: '26px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 700, borderRadius: '2px'}} title="Bold">B</button>
                  <button className="tb-font-btn" data-action="text-italic" style={{width: '26px', height: '26px', border: 'none', background: 'transparent', cursor: 'pointer', fontStyle: 'italic', borderRadius: '2px'}} title="Italic">I</button>
                  <button className="tb-font-btn" data-action="text-underline" style={{width: '26px', height: '26px', border: 'none', background: 'transparent', cursor: 'pointer', textDecoration: 'underline', borderRadius: '2px'}} title="Underline">U</button>
                  <button className="tb-font-btn" data-action="text-inside" style={{width: '26px', height: '26px', border: 'none', background: 'transparent', cursor: 'pointer', borderRadius: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center'}} title="Move Inside/Outside"><span className="material-symbols-outlined" style={{fontSize: '16px'}}>vertical_align_center</span></button>
                </div>
                <div style={{display: 'flex', background: 'rgba(0,0,0,0.03)', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.06)', padding: '4px', gap: '6px', alignItems: 'center'}}>
                  {[...fixedTexts, ...recentTextColors].map((color, i) => (
                    <button key={'text'+i} type="button" style={{width: '20px', height: '20px', borderRadius: '50%', background: color === 'transparent' ? 'url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVQIW2NkYGD4z8DAwMgAI0AMDA4YAQc0D+oAAAAASUVORK5CYII=)' : color, border: activeText === color ? '2px solid #4f46e5' : '1px solid rgba(0,0,0,0.1)', cursor: 'pointer', boxShadow: activeText === color ? '0 0 0 2px rgba(79, 70, 229, 0.2)' : 'none'}} onClick={() => { 
                      document.dispatchEvent(new CustomEvent('color-picker-input', { detail: { id: 'picker-text', color } }));
                      document.dispatchEvent(new CustomEvent('color-picker-closed', { detail: { id: 'picker-text', color } }));
                      setActiveText(color);
                    }} title={color}></button>
                  ))}
                  <button type="button" style={{width: '20px', height: '20px', borderRadius: '50%', background: '#f4f4f5', border: '1px dashed rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(0,0,0,0.5)', cursor: 'pointer', position: 'relative'}} title="Custom Color">
                    <span style={{fontSize: '12px', fontWeight: 500}}>+</span>
                    <input type="color" id="picker-text" title="Text Color" defaultValue="#1e293b" style={{position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer'}}
                      onInput={(e: any) => document.dispatchEvent(new CustomEvent('color-picker-input', { detail: { id: 'picker-text', color: e.target.value } }))}
                      onChange={(e: any) => document.dispatchEvent(new CustomEvent('color-picker-closed', { detail: { id: 'picker-text', color: e.target.value } }))}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>
          </div>
          
          <div id="edge-formatting-tools" style={{display: 'none', gap: '4px'}}>
            <div className="tb-dropdown-container">
              <button className="tb-dropdown-btn" type="button" title="Line Style">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><path d="M5 12h14" /></svg>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 14, height: 14, marginLeft: '2px'}}><polyline points="6 9 12 15 18 9" /></svg>
              </button>
              
              <div className="tb-dropdown-menu" style={{width: '120px', padding: '8px', borderRadius: '10px', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(15, 23, 42, 0.06)', border: '1px solid #e2e8f0', left: 0}}>
                
                <div className="tb-dropdown-item" data-edge-action="line-solid" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px', marginBottom: '4px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}><line x1="0" y1="12" x2="80" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="edge-stroke-preview" /></svg>
                </div>

                <div className="tb-dropdown-item" data-edge-action="line-dashed" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px', marginBottom: '4px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}><line x1="0" y1="12" x2="80" y2="12" stroke="currentColor" strokeWidth="2" strokeDasharray="6,4" strokeLinecap="round" className="edge-stroke-preview" /></svg>
                </div>

                <div className="tb-dropdown-item" data-edge-action="line-dotted" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px', marginBottom: '4px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}><line x1="0" y1="12" x2="80" y2="12" stroke="currentColor" strokeWidth="2" strokeDasharray="2,5" strokeLinecap="round" className="edge-stroke-preview" /></svg>
                </div>

                <div className="tb-dropdown-item" data-edge-action="line-curved" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}><path d="M 0 16 Q 40 0 80 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="edge-stroke-preview" /></svg>
                </div>

              </div>
            </div>

            <div className="tb-dropdown-container">
              <button className="tb-dropdown-btn" type="button" title="Arrowhead Style">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><path d="M5 12h14" /><path d="M15 16l4-4-4-4" /></svg>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 14, height: 14, marginLeft: '2px'}}><polyline points="6 9 12 15 18 9" /></svg>
              </button>
              
              <div className="tb-dropdown-menu" style={{width: '120px', padding: '8px', borderRadius: '10px', boxShadow: '0 8px 24px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(15, 23, 42, 0.06)', border: '1px solid #e2e8f0', left: 0}}>

                <div className="tb-dropdown-item" data-edge-action="arrowhead-solid" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px', marginBottom: '4px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}>
                    <line x1="0" y1="12" x2="68" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="edge-stroke-preview" />
                    <polygon points="68,7 80,12 68,17" fill="currentColor" className="edge-fill-preview" />
                  </svg>
                </div>

                <div className="tb-dropdown-item" data-edge-action="arrowhead-open" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px', marginBottom: '4px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}>
                    <line x1="0" y1="12" x2="74" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="edge-stroke-preview" />
                    <path d="M 68 7 L 78 12 L 68 17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="edge-stroke-preview" />
                  </svg>
                </div>

                <div className="tb-dropdown-item" data-edge-action="arrowhead-diamond" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px', marginBottom: '4px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}>
                    <line x1="0" y1="12" x2="66" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="edge-stroke-preview" />
                    <polygon points="72,6 80,12 72,18 64,12" fill="currentColor" className="edge-fill-preview" />
                  </svg>
                </div>

                <div className="tb-dropdown-item" data-edge-action="arrowhead-circle" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '36px', borderRadius: '6px'}}>
                  <svg width="80" height="24" style={{flexShrink: 0}}>
                    <line x1="0" y1="12" x2="70" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="edge-stroke-preview" />
                    <circle cx="74" cy="12" r="5" fill="currentColor" className="edge-fill-preview" />
                  </svg>
                </div>

              </div>
            </div>
          </div>
          
          <div className="tb-divider" />
          <button className="tb-btn" type="button" title="Undo" id="btn-undo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><path strokeLinecap="round" strokeLinejoin="round" d="M3 7v6h6" /><path strokeLinecap="round" strokeLinejoin="round" d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13" /></svg>
          </button>
          <button className="tb-btn" type="button" title="Redo" id="btn-redo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><path strokeLinecap="round" strokeLinejoin="round" d="M21 7v6h-6" /><path strokeLinecap="round" strokeLinejoin="round" d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13" /></svg>
          </button>
        </div>

        {/* Zoom HUD */}
        <div className="canvas-hud">
          <div className="hud-zoom">
            <div className="hud-zoom__btn" id="hud-zoom-out" title="Zoom Out">−</div>
            <div className="hud-zoom__level" id="hud-zoom-level" title="Reset Zoom">100%</div>
            <div className="hud-zoom__btn" id="hud-zoom-in" title="Zoom In">+</div>
          </div>
          <div className="hud-btn" id="hud-fit" title="Fit to Screen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polyline points="4 14 4 20 10 20" /><polyline points="20 10 20 4 14 4" /><line x1={14} y1={10} x2={21} y2={3} /><line x1={3} y1={21} x2={10} y2={14} /></svg> Fit</div>
          <div className="hud-divider" />
          <div className="hud-icon-btn active" id="hud-snap" title="Snap to Grid"><svg viewBox="0 0 24 24" fill="currentColor"><circle cx="4" cy="4" r="2" /><circle cx="12" cy="4" r="2" /><circle cx="20" cy="4" r="2" /><circle cx="4" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="20" cy="12" r="2" /><circle cx="4" cy="20" r="2" /><circle cx="12" cy="20" r="2" /><circle cx="20" cy="20" r="2" /></svg></div>
          <div className="hud-divider" />
          <div className="hud-btn" id="hud-reset" title="Reset Default Styles"><span className="material-symbols-outlined" style={{fontSize: '18px'}}>restart_alt</span></div>
          <div className="hud-btn" id="hud-clear" title="Clear Canvas"><span className="material-symbols-outlined" style={{fontSize: '18px', color: '#ef4444'}}>delete</span></div>
        </div>
        {/* SVG Engine Engine */}
        <svg id="model-svg" width="100%" height="100%" style={{display: 'block'}} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }} onDrop={handleCanvasDrop}>
          <defs>
            <pattern id="dot-grid" width={20} height={20} patternUnits="userSpaceOnUse">
              <circle cx={2} cy={2} r={1} fill="rgba(100,116,139,0.25)" />
            </pattern>
            <marker id="arrowhead" markerWidth={10} markerHeight={7} refX={9} refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-text-secondary)" style={{pointerEvents: 'none'}} />
            </marker>
            <marker id="arrowhead-selected" markerWidth={10} markerHeight={7} refX={9} refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-accent)" style={{pointerEvents: 'none'}} />
            </marker>
            <marker id="arrowhead-open" markerWidth={10} markerHeight={7} refX={9} refY="3.5" orient="auto">
              <polyline points="0 0, 10 3.5, 0 7" fill="none" stroke="var(--color-text-secondary)" strokeWidth="1.5" style={{pointerEvents: 'none'}} />
            </marker>
            <marker id="arrowhead-open-selected" markerWidth={10} markerHeight={7} refX={9} refY="3.5" orient="auto">
              <polyline points="0 0, 10 3.5, 0 7" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" style={{pointerEvents: 'none'}} />
            </marker>
          </defs>
          <rect id="bg-rect" width="100%" height="100%" fill="url(#dot-grid)" />
          <g id="zoom-layer">
            <g id="edges-layer" />
            <g id="nodes-layer" />
            <g id="guides-layer" />
          </g>
        </svg>
        <div className="canvas-empty-hint" id="canvas-empty-hint">Drag variables from the left panel to create constructs</div>
      </main>
    </div>{/* /app-body */}
  </div>{/* /view-model */}
  <div id="view-results" className="view-panel" style={{display: 'none'}}>
    {/* ═══ APP BODY ═══ */}
    <div className="app-body">
      {/* ─── Results Hierarchy Tree (Left) ─── */}
      <aside className="results-sidebar" id="results-sidebar">
        <div className="results-sidebar__search">
          <div className="results-sidebar__search-wrap">
            <svg className="results-sidebar__search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={11} cy={11} r={8} /><line x1={21} y1={21} x2="16.65" y2="16.65" /></svg>
            <input type="text" className="results-sidebar__search-input" placeholder="Filter results... (⌘F)" />
          </div>
        </div>
        <div className="results-sidebar__tree" id="results-tree">
          {/* Graphical output */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Graphical output</span>
            </div>
            <div className="tree-section__items">
              <a href="#" className="tree-item">Path model graph</a>
              <a href="#" className="tree-item">Outer model loadings</a>
            </div>
          </div>
          {/* Final results */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Final results</span>
            </div>
            <div className="tree-section__items">
              <a href="#" className="tree-item active">
                <div className="tree-item__left">
                  <div className="tree-item__dot" />
                  <span>Path coefficients</span>
                </div>
                <span className="tree-item__size">7×7</span>
              </a>
              <a href="#" className="tree-item">Total indirect effects</a>
              <a href="#" className="tree-item tree-item--sub">Specific indirect effects</a>
              <a href="#" className="tree-item">Total effects</a>
              <a href="#" className="tree-item">Outer loadings</a>
              <a href="#" className="tree-item">Outer weights</a>
              <a href="#" className="tree-item">Latent variables</a>
              <a href="#" className="tree-item">Residuals</a>
            </div>
          </div>
          {/* Quality criteria */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Quality criteria</span>
            </div>
            <div className="tree-section__items">
              <a href="#" className="tree-item">R-square (R²)</a>
              <a href="#" className="tree-item">f-square (f²)</a>
              <a href="#" className="tree-item">Construct reliability and validity</a>
              <a href="#" className="tree-item">Discriminant validity</a>
              <a href="#" className="tree-item">Collinearity statistics (VIF)</a>
              <a href="#" className="tree-item">Model fit</a>
              <a href="#" className="tree-item">Model selection criteria</a>
            </div>
          </div>
          {/* Algorithm */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Algorithm</span>
            </div>
            <div className="tree-section__items">
              <a href="#" className="tree-item">Setting</a>
              <a href="#" className="tree-item">Stop criterion changes</a>
              <a href="#" className="tree-item">Post-hoc power analysis</a>
              <a href="#" className="tree-item">Execution log</a>
            </div>
          </div>
          {/* Model and data */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Model and data</span>
            </div>
            <div className="tree-section__items">
              <a href="#" className="tree-item">Inner model</a>
              <a href="#" className="tree-item">Outer model</a>
              <a href="#" className="tree-item">Indicator data (original)</a>
              <a href="#" className="tree-item">Indicator data (standardized)</a>
              <a href="#" className="tree-item">Indicator data (correlations)</a>
            </div>
          </div>
        </div>
      </aside>
      {/* ─── Center Results Area ─── */}
      <main className="results-main">
        {/* Header Area */}
        <div className="report-header">
          <div className="report-header__top">
            <div>
              <h1 className="report-header__title">
                Path Coefficients
                <span className="report-header__title-sub">β (beta)</span>
              </h1>
              <p className="report-header__subtitle">Standardized beta coefficients between endogenous and exogenous latent constructs.</p>
            </div>
            <div className="view-toggle">
              <div className="view-toggle__btn active">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
                Matrix View
              </div>
              <div className="view-toggle__btn">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M4 6h16M4 10h16M4 14h16M4 18h16" /></svg>
                List View (7 paths)
              </div>
            </div>
          </div>
          <div className="report-filters">
            <div className="report-filters__left">
              <label className="report-filter-label">
                <input type="checkbox" defaultChecked />
                <span className="report-filter-label__text">Highlight Significant (p &lt; 0.05)</span>
              </label>
              <label className="report-filter-label">
                <input type="checkbox" defaultChecked />
                <span className="report-filter-label__text-muted">Show t-statistics</span>
              </label>
            </div>
            <div className="report-filters__right">
              <button className="report-action-btn" type="button">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" /></svg>
                Copy Table
              </button>
              <button className="report-action-btn" type="button">Export CSV</button>
            </div>
          </div>
        </div>
        {/* Table Area */}
        <div className="table-container">
          <div className="scientific-table-wrap">
            <table className="scientific-table">
              <colgroup>
                <col style={{width: 176}} />
                <col style={{width: '12%'}} />
                <col style={{width: '12%'}} />
                <col style={{width: '12%'}} />
                <col style={{width: '12%'}} />
                <col style={{width: '12%'}} />
                <col style={{width: '12%'}} />
                <col style={{width: '12%'}} />
              </colgroup>
              <thead>
                <tr>
                  <th>Construct</th>
                  <th>ATTR</th>
                  <th>COMP</th>
                  <th>CSOR</th>
                  <th>CUSA</th>
                  <th>LIKE</th>
                  <th>PERF</th>
                  <th>QUAL</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#6366f1'}} />
                      <span className="construct-name">ATTR</span>
                      <span className="construct-role">(Endo)</span>
                    </div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#0ea5e9'}} />
                      <span className="construct-name">COMP</span>
                      <span className="construct-role">(Exo)</span>
                    </div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-sig">
                    <div className="cell-value">0.148<span className="cell-stars">*</span></div>
                    <div className="cell-stats">t=2.114 · p=0.035</div>
                  </td>
                  <td className="cell-sig--strong">
                    <div className="cell-value">0.344<span className="cell-stars">***</span></div>
                    <div className="cell-stats">t=4.912 · p&lt;0.001</div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#f59e0b'}} />
                      <span className="construct-name">CSOR</span>
                      <span className="construct-role">(Exo)</span>
                    </div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td>
                    <div className="cell-ns">0.061</div>
                    <div className="cell-stats">t=0.982 · p=0.326</div>
                  </td>
                  <td className="cell-sig">
                    <div className="cell-value">0.175<span className="cell-stars">**</span></div>
                    <div className="cell-stats">t=2.834 · p=0.005</div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#10b981'}} />
                      <span className="construct-name">CUSA</span>
                      <span className="construct-role">(Endo)</span>
                    </div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-sig--very-strong">
                    <div className="cell-value">0.428<span className="cell-stars">***</span></div>
                    <div className="cell-stats">t=7.185 · p&lt;0.001</div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#a855f7'}} />
                      <span className="construct-name">LIKE</span>
                      <span className="construct-role">(Endo)</span>
                    </div>
                  </td>
                  <td className="cell-sig--very-strong">
                    <div className="cell-value">0.536<span className="cell-stars">***</span></div>
                    <div className="cell-stats">t=8.411 · p&lt;0.001</div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#f43f5e'}} />
                      <span className="construct-name">PERF</span>
                      <span className="construct-role">(Exo)</span>
                    </div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-sig--strong">
                    <div className="cell-value">0.291<span className="cell-stars">***</span></div>
                    <div className="cell-stats">t=3.890 · p&lt;0.001</div>
                  </td>
                  <td>
                    <div className="cell-ns">0.089</div>
                    <div className="cell-stats">t=1.452 · p=0.147</div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
                <tr>
                  <td>
                    <div className="construct-label">
                      <div className="construct-dot" style={{background: '#14b8a6'}} />
                      <span className="construct-name">QUAL</span>
                      <span className="construct-role">(Exo)</span>
                    </div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                  <td className="cell-sig--strong">
                    <div className="cell-value">0.384<span className="cell-stars">***</span></div>
                    <div className="cell-stats">t=4.821 · p&lt;0.001</div>
                  </td>
                  <td>
                    <div className="cell-ns">0.042</div>
                    <div className="cell-stats">t=0.672 · p=0.502</div>
                  </td>
                  <td className="cell-empty">—</td>
                  <td className="cell-empty">—</td>
                </tr>
              </tbody>
            </table>
            <div className="sig-legend">
              <span style={{color: 'var(--color-text-secondary)', fontWeight: 500}}>Significance Legend:</span>
              <div className="sig-legend__item"><span className="sig-legend__stars">*</span> p &lt; 0.05</div>
              <div className="sig-legend__item"><span className="sig-legend__stars">**</span> p &lt; 0.01</div>
              <div className="sig-legend__item"><span className="sig-legend__stars">***</span> p &lt; 0.001</div>
              <span style={{flex: 1}} />
              <div style={{fontFamily: 'var(--font-sans)'}}>Based on 5000 bootstrap subsamples</div>
            </div>
          </div>
        </div>
      </main>
    </div>{/* /app-body */}
  </div>{/* /view-results */}
  {datasetToImport && (
    <DataManagerModal
      dataset={datasetToImport}
      onImport={(validatedDataset) => {
        setActiveDataset(validatedDataset);
        setDatasetToImport(null);
      }}
      onCancel={() => setDatasetToImport(null)}
    />
  )}

    </div>
  );
};

export default ModelEditor;
