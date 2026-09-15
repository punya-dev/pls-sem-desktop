import React, { useEffect, useState, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { initModelCanvas, exportModelSpec, getModelCanvasState, loadModelCanvasState } from '../utils/model-canvas';
import { DataManagerModal } from '../components/DataManagerModal';
import { BootstrapModal } from '../components/BootstrapModal';
import type { ParsedDataset } from '../utils/dataset-parser';
import { parseDatasetFile, processData } from '../utils/dataset-parser';
import { api, type ValidationResponse } from '../utils/api';

import { Upload } from 'lucide-react';
import '../model-canvas.css';
import '../results.css';

interface PathStat {
  from: string;
  to: string;
  beta: number;
  mean: number;
  stdev: number;
  tStat: number;
  pValue: number;
  stars: string;
}

const CONSTRUCT_LIST = [
  { code: 'ATTR', name: 'ATTR', role: 'Endo', color: '#6366f1' },
  { code: 'COMP', name: 'COMP', role: 'Exo', color: '#0ea5e9' },
  { code: 'CSOR', name: 'CSOR', role: 'Exo', color: '#f59e0b' },
  { code: 'CUSA', name: 'CUSA', role: 'Endo', color: '#10b981' },
  { code: 'LIKE', name: 'LIKE', role: 'Endo', color: '#a855f7' },
  { code: 'PERF', name: 'PERF', role: 'Exo', color: '#f43f5e' },
  { code: 'QUAL', name: 'QUAL', role: 'Exo', color: '#14b8a6' },
];

const RAW_PATHS = [
  { from: 'COMP', to: 'CUSA', baseBeta: 0.148, baseT: 2.114, baseP: 0.035 },
  { from: 'COMP', to: 'LIKE', baseBeta: 0.344, baseT: 4.912, baseP: 0.0005 },
  { from: 'COMP', to: 'PERF', baseBeta: 0.315, baseT: 4.418, baseP: 0.0003 },
  { from: 'COMP', to: 'ATTR', baseBeta: 0.218, baseT: 3.105, baseP: 0.002 },
  { from: 'CSOR', to: 'CUSA', baseBeta: 0.061, baseT: 0.982, baseP: 0.326 },
  { from: 'CSOR', to: 'LIKE', baseBeta: 0.175, baseT: 2.834, baseP: 0.005 },
  { from: 'CSOR', to: 'ATTR', baseBeta: 0.134, baseT: 2.041, baseP: 0.041 },
  { from: 'CSOR', to: 'QUAL', baseBeta: 0.288, baseT: 3.962, baseP: 0.0004 },
  { from: 'CUSA', to: 'LIKE', baseBeta: 0.428, baseT: 7.185, baseP: 0.0001 },
  { from: 'CUSA', to: 'ATTR', baseBeta: 0.252, baseT: 3.518, baseP: 0.0008 },
  { from: 'LIKE', to: 'ATTR', baseBeta: 0.536, baseT: 8.411, baseP: 0.0001 },
  { from: 'PERF', to: 'CUSA', baseBeta: 0.291, baseT: 3.890, baseP: 0.0002 },
  { from: 'PERF', to: 'LIKE', baseBeta: 0.089, baseT: 1.452, baseP: 0.147 },
  { from: 'PERF', to: 'ATTR', baseBeta: 0.267, baseT: 3.712, baseP: 0.0003 },
  { from: 'QUAL', to: 'CUSA', baseBeta: 0.384, baseT: 4.821, baseP: 0.0002 },
  { from: 'QUAL', to: 'LIKE', baseBeta: 0.042, baseT: 0.672, baseP: 0.502 },
  { from: 'QUAL', to: 'ATTR', baseBeta: 0.195, baseT: 2.894, baseP: 0.004 },
  { from: 'QUAL', to: 'PERF', baseBeta: 0.462, baseT: 6.940, baseP: 0.0001 },
  { from: 'ATTR', to: 'CUSA', baseBeta: 0.112, baseT: 1.984, baseP: 0.047 },
  { from: 'ATTR', to: 'PERF', baseBeta: 0.168, baseT: 2.312, baseP: 0.021 },
  { from: 'ATTR', to: 'LIKE', baseBeta: 0.205, baseT: 2.945, baseP: 0.003 },
];

const ModelEditor = () => {
  const navigate = useNavigate();
  const { workspaces, activeWorkspaceId, studies, activeStudyId, activeModelId, models, datasetsByStudy, setStudyDataset, touchStudy, openTab } = useStore();
  
  const activeWorkspace = workspaces.find(w => w.id === activeWorkspaceId);
  const activeStudy = studies.find(s => s.id === activeStudyId);
  const activeModel = models.find(model => model.id === activeModelId);

  const [currentView, setCurrentView] = useState<'model' | 'results'>('model');
  const [hasCalculated, setHasCalculated] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [calcSeed, setCalcSeed] = useState(1);
  const [resultsViewMode, setResultsViewMode] = useState<'matrix' | 'list'>('matrix');
  const [highlightSignificant, setHighlightSignificant] = useState(true);
  const [showTStats, setShowTStats] = useState(true);
  const [resultsSearchQuery, setResultsSearchQuery] = useState('');

  const [datasetToImport, setDatasetToImport] = useState<ParsedDataset | null>(null);
  const [activeDataset, setActiveDataset] = useState<ParsedDataset | null>(() => activeStudyId ? datasetsByStudy[activeStudyId] ?? null : null);
  const [isImporting, setIsImporting] = useState(false);
  const [isBootstrapModalOpen, setIsBootstrapModalOpen] = useState(false);
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

  const [isSaving, setIsSaving] = useState(false);
  const [saveToast, setSaveToast] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [validationModal, setValidationModal] = useState<ValidationResponse | null>(null);
  const [validationSuccessToast, setValidationSuccessToast] = useState<string | null>(null);
  const [plsResults, setPlsResults] = useState<any>(null);
  const [activeResultTab, setActiveResultTab] = useState<string>('path_coefficients');
  const [resultViewMode, setResultViewMode] = useState<'matrix' | 'list'>('matrix');

  useEffect(() => {
    if (activeStudyId && datasetsByStudy[activeStudyId]) {
      const ds = datasetsByStudy[activeStudyId];
      setActiveDataset(ds);
      // If dataset exists in store, ensure it is synced to the SQLite project file
      if (activeStudy?.path && ds.rows && ds.rows.length > 0) {
        api.loadProjectData(activeStudy.path).then((dataRes) => {
          if (!dataRes || !Array.isArray(dataRes.rows) || dataRes.rows.length === 0) {
            const headers = ds.variables.map(v => v.name);
            api.saveProjectDataJson(activeStudy.path, ds.filename || 'dataset', headers, ds.rows).catch(console.warn);
          }
        }).catch(console.warn);
      }
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
    try {
      event.dataTransfer.setData('text/plain', variableName);
      event.dataTransfer.setData('text', variableName);
    } catch {
      // Ignore if webview restricts dataTransfer.setData
    }

    event.dataTransfer.effectAllowed = 'copy';
    (window as any).__draggedVariable = variableName;
  };

  const handleCanvasDrop = (event: React.DragEvent<any>) => {
    event.preventDefault();
    event.stopPropagation();

    let variableName = '';

    try {
      variableName =
        event.dataTransfer?.getData('text/plain') ||
        event.dataTransfer?.getData('text') ||
        '';
    } catch {
      // Ignore
    }

    if (!variableName) {
      variableName = (window as any).__draggedVariable || '';
    }

    (window as any).__draggedVariable = null;

    if (variableName) {
      (window as any).dropModelVariable?.(
        variableName,
        event.clientX,
        event.clientY
      );
    }
    if (!variableName) {
      variableName = (window as any).__draggedVariable || '';
    }
    (window as any).__draggedVariable = null;
    if (variableName) {
      (window as any).dropModelVariable?.(
        variableName,
        event.clientX,
        event.clientY
      );
    }
  };

  const switchView = (view: 'model' | 'results') => {
    const viewSlider = document.getElementById('main-view-slider');
    const viewModel = document.getElementById('view-model');
    const viewResults = document.getElementById('view-results');
    const sliderBtns = viewSlider?.querySelectorAll('.view-slider__btn');
    const sliderBg = viewSlider?.querySelector('.view-slider__bg');

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
  };

  const handleSaveModel = async () => {
    if (!activeStudy?.path) {
      alert('Please open or select an active project study first.');
      return;
    }

    try {
      setIsSaving(true);

      const spec = exportModelSpec();
      const layout = getModelCanvasState();
      const res = await api.saveProjectModel(activeStudy.path, spec, layout);

      if (res.error) {
        alert('Failed to save model: ' + res.error);
      } else {
        setSaveToast('Model saved successfully');
        setTimeout(() => setSaveToast(null), 2500);
      }
    } catch (err: any) {
      alert('Error saving model: ' + err?.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCalculate = async () => {
    if (!activeStudy?.path) {
      alert('Please open or select an active project study first.');
      return;
    }

    try {
      setIsCalculating(true);

      const spec = exportModelSpec();
      const layout = getModelCanvasState();

      // Ensure dataset is saved to project file if activeDataset is present
      const datasetHeaders = activeDataset?.variables?.map(v => v.name);

      if (
        activeDataset &&
        Array.isArray(activeDataset.rows) &&
        activeDataset.rows.length > 0
      ) {
        try {
          await api.saveProjectDataJson(
            activeStudy.path,
            activeDataset.filename || 'dataset',
            datasetHeaders || [],
            activeDataset.rows
          );
        } catch (err) {
          console.warn(
            'Failed auto-saving active dataset before calculate:',
            err
          );
        }
      }

      // 1. Validate model spec with backend
      const valRes = await api.validateModel(
        spec,
        activeStudy.path,
        datasetHeaders
      );

      if (!valRes.is_valid) {
        setValidationModal(valRes);
        return;
      }

      // 2. Auto-save model
      await api.saveProjectModel(activeStudy.path, spec, layout);

      // 3. Execute PLS-SEM algorithm
      const runRes = await api.runPlsModel(
        activeStudy.path,
        spec,
        {
          columns: datasetHeaders,
          rows: activeDataset?.rows,
          dataset_name: activeDataset?.filename,
        }
      );

      if (runRes.error) {
        alert('PLS-SEM calculation failed: ' + runRes.error);
        return;
      }

      if (runRes.results) {
        setPlsResults(runRes.results);
      }

      setValidationSuccessToast(
        `PLS-SEM Calculation Complete! Converged in ${
          runRes.results?.iterations || 0
        } iterations`
      );

      setTimeout(() => setValidationSuccessToast(null), 3500);

      // Show view slider and switch to results view
      const viewSlider = document.getElementById('main-view-slider');

      if (viewSlider) {
        (viewSlider as HTMLElement).style.display = 'flex';
      }

      switchView('results');
    } catch (err: any) {
      alert('Error calculating model: ' + err?.message);
    } finally {
      setIsCalculating(false);
    }
  };
  };

  useEffect(() => {
    if (activeStudy?.path) {
      api.loadProjectResults(activeStudy.path, 'pls').then((res) => {
        if (res && res.results) {
          setPlsResults(res.results);
          const viewSlider = document.getElementById('main-view-slider');
          if (viewSlider) {
            (viewSlider as HTMLElement).style.display = 'flex';
          }
        }
      }).catch(() => {});
    }
  }, [activeStudy?.path]);

  const fmt = (val: any, decimals: number = 4): string => {
    if (val === undefined || val === null || isNaN(Number(val))) return '—';
    return Number(val).toFixed(decimals);
  };

  const { constructNameMap, indicatorNameMap } = useMemo(() => {
    const cMap: Record<string, string> = {};
    const iMap: Record<string, string> = {};

    const cleanStem = (name: string) => {
      if (!name) return '';
      return name.replace(/[_\-\s.]*\d+$/i, '').trim() || name;
    };

    const deriveName = (indicatorNames: string[]) => {
      if (!indicatorNames || indicatorNames.length === 0) return '';
      const stems = indicatorNames.map(cleanStem).filter(Boolean);
      if (stems.length === 0) return '';
      const first = stems[0].toUpperCase();
      if (stems.every(s => s.toUpperCase() === first)) return first;
      let prefix = stems[0];
      for (let i = 1; i < stems.length; i++) {
        while (!stems[i].toUpperCase().startsWith(prefix.toUpperCase()) && prefix.length > 0) {
          prefix = prefix.slice(0, -1);
        }
      }
      prefix = prefix.replace(/[_\-\s.]+$/, '').trim();
      return prefix.length >= 2 ? prefix.toUpperCase() : first;
    };

    // 1. From canvas state
    try {
      const canvasState = getModelCanvasState();
      if (canvasState && Array.isArray(canvasState.nodes)) {
        const latentNodes = canvasState.nodes.filter((n: any) => n.isLatent !== false && !n.isText);
        const indNodes = canvasState.nodes.filter((n: any) => n.isLatent === false && !n.isText);

        indNodes.forEach((ind: any) => {
          iMap[ind.id] = ind.label;
        });

        latentNodes.forEach((ln: any) => {
          const childInds = indNodes.filter((i: any) => i.parentId === ln.id).map((i: any) => i.label);
          let name = ln.label;
          if (!name || name.startsWith('node_') || name.toUpperCase().startsWith('LATENT') || name.toUpperCase().startsWith('LV_')) {
            const derived = deriveName(childInds);
            if (derived) name = derived;
          }
          cMap[ln.id] = name || ln.id;
        });
      }
    } catch (e) {}

    // 2. From plsResults if backend returned them
    if (plsResults?.construct_names) {
      Object.entries(plsResults.construct_names).forEach(([cid, cname]) => {
        if (!cMap[cid] || cMap[cid].startsWith('node_')) {
          cMap[cid] = String(cname);
        }
      });
    }
    if (plsResults?.indicator_names) {
      Object.entries(plsResults.indicator_names).forEach(([iid, iname]) => {
        if (!iMap[iid]) {
          iMap[iid] = String(iname);
        }
      });
    }

    return { constructNameMap: cMap, indicatorNameMap: iMap };
  }, [plsResults]);

  const getConstructName = (cid: string): string => constructNameMap[cid] || cid;
  const getIndicatorName = (iid: string): string => indicatorNameMap[iid] || iid;

  const resultConstructs: string[] = useMemo(() => {
    if (!plsResults) return [];
    const fromLoadings = Object.keys(plsResults.measurement?.outer_loadings || {});
    if (fromLoadings.length > 0) return fromLoadings;
    return Object.keys(plsResults.reliability_and_validity?.ave || {});
  }, [plsResults]);

  const constructPalette: Record<string, string> = useMemo(() => {
    const colors = ['#6366f1', '#0ea5e9', '#f59e0b', '#10b981', '#a855f7', '#f43f5e', '#14b8a6', '#ec4899', '#8b5cf6'];
    const map: Record<string, string> = {};
    resultConstructs.forEach((c, idx) => {
      map[c] = colors[idx % colors.length];
    });
    return map;
  }, [resultConstructs]);

  const reportTabDetails = useMemo(() => {
    switch (activeResultTab) {
      case 'path_coefficients':
        return {
          title: 'Path Coefficients',
          badge: 'β (beta)',
          subtitle: 'Standardized beta coefficients between endogenous and exogenous latent constructs.',
        };
      case 'total_effects':
        return {
          title: 'Total & Indirect Effects',
          badge: 'Direct + Indirect',
          subtitle: 'Cumulative relationships and mediation decomposition across the structural model.',
        };
      case 'outer_loadings':
        return {
          title: 'Outer Loadings',
          badge: 'λ (lambda)',
          subtitle: 'Bivariate correlations between each indicator and its associated latent construct score.',
        };
      case 'outer_weights':
        return {
          title: 'Outer Weights',
          badge: 'w',
          subtitle: 'Relative contribution weights of indicators to their latent construct scores.',
        };
      case 'r_squared':
        return {
          title: 'R-Square (R²)',
          badge: 'R² & Adj R²',
          subtitle: 'Coefficient of determination measuring variance explained for endogenous constructs.',
        };
      case 'f_squared':
        return {
          title: 'f-Square Effect Sizes',
          badge: 'f²',
          subtitle: 'Cohen\'s f² effect size of omitted predictor on endogenous construct R².',
        };
      case 'reliability':
        return {
          title: 'Construct Reliability & Validity',
          badge: 'α, CR, ρA, AVE',
          subtitle: 'Internal consistency reliability (Cronbach\'s α, CR, rho_A) and convergent validity (AVE).',
        };
      case 'discriminant':
        return {
          title: 'Discriminant Validity',
          badge: 'HTMT & Fornell-Larcker',
          subtitle: 'Assessment of construct distinction via Heterotrait-Monotrait ratio and Fornell-Larcker criterion.',
        };
      case 'collinearity':
        return {
          title: 'Collinearity Statistics (VIF)',
          badge: 'VIF',
          subtitle: 'Variance Inflation Factors evaluating multicollinearity among predictors and indicators.',
        };
      case 'construct_scores':
        return {
          title: 'Latent Variable Scores',
          badge: 'Y (standardized)',
          subtitle: 'Estimated case-level construct scores standardized to zero mean and unit variance.',
        };
      case 'bootstrap_significance':
        return {
          title: 'Bootstrap Significance Testing',
          badge: 'p-values, t-stats, 95% CI',
          subtitle: 'Non-parametric bootstrap distributions, standard errors, t-statistics, p-values, and 95% confidence intervals.',
        };
      default:
        return {
          title: 'PLS-SEM Results',
          badge: 'PLS',
          subtitle: 'Estimation results from the PLS-SEM engine.',
        };
    }
  }, [activeResultTab]);

  const handleCopyCurrentTable = () => {
    const tableEl = document.querySelector('.scientific-table');
    if (!tableEl) return;
    let tsv = '';
    const rows = tableEl.querySelectorAll('tr');
    rows.forEach(r => {
      const cells = r.querySelectorAll('th, td');
      const line = Array.from(cells).map(c => c.textContent?.trim().replace(/\s+/g, ' ') || '').join('\t');
      tsv += line + '\n';
    });
    navigator.clipboard.writeText(tsv);
    setValidationSuccessToast('Table copied to clipboard (TSV format)');
    setTimeout(() => setValidationSuccessToast(null), 2500);
  };

  const handleExportCurrentTable = () => {
    const tableEl = document.querySelector('.scientific-table');
    if (!tableEl) return;
    let csv = '';
    const rows = tableEl.querySelectorAll('tr');
    rows.forEach(r => {
      const cells = r.querySelectorAll('th, td');
      const line = Array.from(cells).map(c => {
        let txt = c.textContent?.trim().replace(/\s+/g, ' ') || '';
        if (txt.includes(',') || txt.includes('"')) {
          txt = `"${txt.replace(/"/g, '""')}"`;
        }
        return txt;
      }).join(',');
      csv += line + '\n';
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeResultTab}_results.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportModel = () => {
    try {
      const spec = exportModelSpec();
      const jsonStr = JSON.stringify(spec, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeStudy?.name || 'model'}_spec.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert('Error exporting model: ' + err?.message);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isInput = e.target instanceof HTMLElement && (
        e.target.tagName === 'INPUT' ||
        e.target.tagName === 'TEXTAREA' ||
        e.target.isContentEditable ||
        (e.target as any).dataset?.editable
      );

      if ((e.key === 'Backspace' || e.key === 'Delete') && !isInput) {
        e.preventDefault();
        if ((window as any).deleteSelectedModelPart) {
          (window as any).deleteSelectedModelPart();
        }
      }

      if ((e.metaKey || e.ctrlKey) && !isInput) {
        if (e.key.toLowerCase() === 'z') {
          e.preventDefault();
          if (e.shiftKey) {
            (window as any).canvasRedo?.();
          } else {
            (window as any).canvasUndo?.();
          }
        } else if (e.key.toLowerCase() === 'y') {
          e.preventDefault();
          (window as any).canvasRedo?.();
        }
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        handleSaveModel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeStudy?.path]);

  useEffect(() => {
    // Add global sync method for color pickers
    (window as any).syncColorPickers = (fill: string, border: string, text: string) => {
      if (fill) setActiveFill(fill);
      if (border) setActiveBorder(border);
      if (text) setActiveText(text);
    };

    // Add a tiny delay to ensure DOM is ready
    const timer = setTimeout(async () => {
      initModelCanvas();

      if (activeStudy?.path) {
        try {
          const modelRes = await api.loadProjectModel(activeStudy.path);
          if (modelRes && modelRes.diagram_layout) {
            loadModelCanvasState(modelRes.diagram_layout);
          }
        } catch (err) {
          console.warn('Could not load saved model layout:', err);
        }
      }

      // Load results script if it exists
      import('../utils/results.js').then((m) => {
        if (m.initResults) m.initResults();
      }).catch(() => {});

    if (variableName) {
      (window as any).dropModelVariable?.(
        variableName,
        event.clientX,
        event.clientY
      );
    }
  };

  const switchView = (view: 'model' | 'results') => {
    const viewSlider = document.getElementById('main-view-slider');
    const viewModel = document.getElementById('view-model');
    const viewResults = document.getElementById('view-results');
    const sliderBtns = viewSlider?.querySelectorAll('.view-slider__btn');
    const sliderBg = viewSlider?.querySelector('.view-slider__bg');

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
  };

  const handleSaveModel = async () => {
    if (!activeStudy?.path) {
      alert('Please open or select an active project study first.');
      return;
    }

    try {
      setIsSaving(true);
      const spec = exportModelSpec();
      const layout = getModelCanvasState();
      const res = await api.saveProjectModel(activeStudy.path, spec, layout);

      if (res.error) {
        alert('Failed to save model: ' + res.error);
      } else {
        setSaveToast('Model saved successfully');
        setTimeout(() => setSaveToast(null), 2500);
      }
    } catch (err: any) {
      alert('Error saving model: ' + err?.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCalculate = async () => {
    if (!activeStudy?.path) {
      alert('Please open or select an active project study first.');
      return;
    }

    try {
      setIsCalculating(true);
      const spec = exportModelSpec();
      const layout = getModelCanvasState();

      const datasetHeaders = activeDataset?.variables?.map(v => v.name);

      if (
        activeDataset &&
        Array.isArray(activeDataset.rows) &&
        activeDataset.rows.length > 0
      ) {
        try {
          await api.saveProjectDataJson(
            activeStudy.path,
            activeDataset.filename || 'dataset',
            datasetHeaders || [],
            activeDataset.rows
          );
        } catch (err) {
          console.warn(
            'Failed auto-saving active dataset before calculate:',
            err
          );
        }
      }

      const valRes = await api.validateModel(
        spec,
        activeStudy.path,
        datasetHeaders
      );

      if (!valRes.is_valid) {
        setValidationModal(valRes);
        return;
      }

      await api.saveProjectModel(activeStudy.path, spec, layout);

      const runRes = await api.runPlsModel(
        activeStudy.path,
        spec,
        {
          columns: datasetHeaders,
          rows: activeDataset?.rows,
          dataset_name: activeDataset?.filename,
        }
      );

      if (runRes.error) {
        alert('PLS-SEM calculation failed: ' + runRes.error);
        return;
      }

      if (runRes.results) {
        setPlsResults(runRes.results);
      }

      setValidationSuccessToast(
        `PLS-SEM Calculation Complete! Converged in ${
          runRes.results?.iterations || 0
        } iterations`
      );

      setTimeout(() => setValidationSuccessToast(null), 3500);

      const viewSlider = document.getElementById('main-view-slider');
      if (viewSlider) {
        (viewSlider as HTMLElement).style.display = 'flex';
      }

      switchView('results');
    } catch (err: any) {
      alert('Error calculating model: ' + err?.message);
    } finally {
      setIsCalculating(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      const viewSlider = document.getElementById('main-view-slider');
      const sliderBtns = viewSlider?.querySelectorAll('.view-slider__btn');

      if (sliderBtns) {
        sliderBtns.forEach(btn => {
          btn.addEventListener('click', (e) => {
            const target = e.currentTarget as HTMLElement | null;
            switchView(
              target?.dataset?.view === 'results' ? 'results' : 'model'
            );
          });
        });
      }
    }, 120);

    return () => clearTimeout(timer);
  }, []);

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
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}
    >

      {/* ═══ TITLE BAR ═══ */}
      <header className="titlebar window-drag">
        <div className="titlebar__left no-drag">
          <div
            className="titlebar__traffic-light-space"
            aria-hidden="true"
          ></div>

          <div
            className="brand"
            onClick={() => navigate('/')}
            role="button"
            tabIndex={0}
            title="Go to Getting Started"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') navigate('/');
            }}
          >
            <svg
              className="brand__logo"
              viewBox="0 0 48 48"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <rect width={48} height={48} rx={10} fill="#6B4EE6" />
              <circle cx={16} cy={16} r={4} fill="#FFFFFF" />
              <circle cx={32} cy={18} r={4} fill="#C7D2FE" />
              <circle cx={20} cy={32} r={5} fill="#EEF2FF" />
              <circle cx={34} cy={32} r="3.5" fill="#A5B4FC" />
              <path
                d="M16 16L32 18M16 16L20 32M20 32L34 32M32 18L34 32"
                stroke="#FFFFFF"
                strokeWidth={2}
                strokeLinecap="round"
                strokeOpacity="0.85"
              />
            </svg>

            <span className="brand__name">CSPLS</span>
          </div>
        </div>

        <div className="titlebar__center no-drag">
          <span className="titlebar__version">CSPLS 1.1</span>
        </div>

        <div className="titlebar__right no-drag">
          <button
            className="icon-btn"
            title="Toggle Theme"
            type="button"
          >
            <span className="material-symbols-outlined">
              light_mode
            </span>
          </button>

          <button
            className="icon-btn"
            title="Settings"
            type="button"
          >
            <span className="material-symbols-outlined">
              settings
            </span>
          </button>

          <span className="v-divider" />

          <div
            className="user-badge"
            role="button"
            tabIndex={0}
          >
            <div className="user-badge__avatar">
              <span>MV</span>
              <span className="user-badge__status" />
            </div>

            <span className="user-badge__name">
              M. Vance
            </span>
          </div>
        </div>
      </header>
  {/* ═══ SUB-HEADER / CONTROL BAR ═══ */}
  <div className="subheader">
    <div className="subheader__breadcrumb">
      <span
        className="subheader__breadcrumb-link"
        id="current-model-workspace"
        onClick={() => {
          if (activeWorkspaceId) {
            openTab({ type: 'workspace', title: activeWorkspace?.name || 'Workspace', workspaceId: activeWorkspaceId });
          }
        }}
      >
        {activeWorkspace?.name || 'Active_Workspace'}
      </span>
      <span className="subheader__breadcrumb-sep">/</span>
      <span
        className="subheader__breadcrumb-link"
        id="current-model-study"
        onClick={() => {
          if (activeWorkspaceId) {
            openTab({ type: 'workspace', title: activeWorkspace?.name || 'Workspace', workspaceId: activeWorkspaceId });
          }
        }}
      >
        {activeStudy?.name || 'Active_Study'}
      </span>
      <span className="subheader__breadcrumb-sep">/</span>
      <span className="subheader__breadcrumb-link" style={{color: 'var(--color-accent)'}}>
        {activeModel ? `${activeModel.name}.splsm` : 'Untitled model.splsm'}
      </span>
    </div>
    <div className="subheader__actions">
      {/* Flush Model | Results Switcher */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', marginRight: '6px' }}>
        <button
          type="button"
          onClick={() => setCurrentView('model')}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontWeight: currentView === 'model' ? 600 : 500,
            color: currentView === 'model' ? 'var(--color-accent, #6B4EE6)' : 'var(--color-text-muted, #64748B)',
            padding: '4px 6px',
            borderBottom: currentView === 'model' ? '2px solid var(--color-accent, #6B4EE6)' : '2px solid transparent',
            transition: 'all 0.15s ease',
          }}
        >
          Model
        </button>
        <span style={{ color: '#CBD5E1', fontSize: '12px' }}>|</span>
        <button
          type="button"
          onClick={() => {
            if (hasCalculated) {
              setCurrentView('results');
            }
          }}
          disabled={!hasCalculated}
          title={hasCalculated ? 'View Results' : 'Please calculate the model first'}
          style={{
            background: 'none',
            border: 'none',
            cursor: hasCalculated ? 'pointer' : 'not-allowed',
            fontWeight: currentView === 'results' ? 600 : 500,
            color: currentView === 'results' 
              ? 'var(--color-accent, #6B4EE6)' 
              : (hasCalculated ? 'var(--color-text-muted, #64748B)' : '#94A3B8'),
            opacity: hasCalculated ? 1 : 0.45,
            padding: '4px 6px',
            borderBottom: currentView === 'results' ? '2px solid var(--color-accent, #6B4EE6)' : '2px solid transparent',
            transition: 'all 0.15s ease',
          }}
        >
          Results
        </button>
      </div>
      <button
        className="subheader__btn subheader__btn--primary"
        id="calculate-btn"
        type="button"
        onClick={handleCalculate}
        disabled={isValidating || isCalculating}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          <polygon points="5 3 19 12 5 21 5 3" />
        </svg>
        {isCalculating
          ? 'Calculating PLS...'
          : (isValidating ? 'Validating...' : 'Calculate')}
      </button>

      <button
        className="subheader__btn"
        id="bootstrap-btn"
        type="button"
        onClick={() => setIsBootstrapModalOpen(true)}
        disabled={isValidating || isCalculating}
        style={{
          marginLeft: '4px',
          backgroundColor: '#eef2ff',
          color: '#4f46e5',
          borderColor: '#c7d2fe',
          fontWeight: 600,
        }}
        title="Run PLS Bootstrapping with significance testing (p-values, t-values, CIs)"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          style={{
            width: 15,
            height: 15,
            marginRight: 4,
          }}
        >
          <path d="M18 20V10M12 20V4M6 20v-6" />
        </svg>
        Bootstrap
      </button>
      </button>
      <div className="subheader__divider" />
      <button
        className="subheader__btn subheader__btn--ghost"
        type="button"
        onClick={handleSaveModel}
        disabled={isSaving}
        title="Save Path Model (Cmd+S)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></svg>
        {isSaving ? 'Saving...' : 'Save'}
      </button>
      <button
        className="subheader__btn subheader__btn--ghost"
        type="button"
        onClick={handleExportModel}
        title="Export Model Spec JSON"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1={12} y1={15} x2={12} y2={3} /></svg>
        Export
      </button>
    </div>
  </div>
  {/* ═══ APP BODY ═══ */}
  <div id="view-model" className="view-panel" style={{ display: currentView === 'model' ? 'flex' : 'none', flex: 1, minHeight: 0, height: '100%', overflow: 'hidden' }}>
    <div className="app-body" style={{ flex: 1, height: '100%', minHeight: 0, display: 'flex', overflow: 'hidden' }}>
      {/* ─── Variable Sidebar (Left) ─── */}
      <aside className="var-sidebar" id="var-sidebar" style={{ height: '100%', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden' }}>
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
          </div>
        )}

        {activeDataset ? (
          <div className="var-sidebar__list" id="var-list" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
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
                      <div 
                        className="var-item" 
                        key={v.name} 
                        data-variable-name={String(v.name ?? '')} 
                        draggable 
                        onDragStart={event => handleVariableDragStart(event, String(v.name ?? ''))}
                        onDragEnd={() => { (window as any).__draggedVariable = null; }}
                      >
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
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 16px', textAlign: 'center' }}>
            <div 
              style={{ 
                width: '100%', 
                border: '1px dashed #CBD5E1', 
                backgroundColor: '#F8FAFC', 
                borderRadius: '8px', 
                padding: '24px 14px', 
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'center', 
                gap: '8px', 
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
              onClick={() => fileInputRef.current?.click()}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#6B4EE6'; e.currentTarget.style.backgroundColor = '#F5F3FF'; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#CBD5E1'; e.currentTarget.style.backgroundColor = '#F8FAFC'; }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '26px', color: '#6B4EE6' }}>upload_file</span>
              <div>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#1E293B' }}>Import Dataset</div>
                <div style={{ fontSize: '11px', color: '#64748B', marginTop: '2px' }}>.csv, .xlsx, or .sav</div>
              </div>
              <button 
                type="button"
                style={{ 
                  marginTop: '6px', 
                  height: '26px', 
                  padding: '0 12px', 
                  borderRadius: '6px', 
                  fontSize: '11px', 
                  fontWeight: 500, 
                  color: 'white', 
                  backgroundColor: '#6B4EE6', 
                  border: 'none', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '4px', 
                  cursor: 'pointer' 
                }}
                disabled={isImporting}
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
              >
                <span>{isImporting ? 'Parsing...' : 'Select File'}</span>
              </button>
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
      <main
        className="canvas-area"
        style={{
          flex: 1,
          height: '100%',
          minHeight: 0,
          position: 'relative',
          overflow: 'hidden'
        }}
        onDragEnter={event => {
          event.preventDefault();
          event.dataTransfer.dropEffect = 'copy';
        }}
        onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }}
        onDrop={handleCanvasDrop}
      >
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
          <button className="tb-btn" type="button" title="Undo (Cmd+Z / Ctrl+Z)" id="btn-undo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><path strokeLinecap="round" strokeLinejoin="round" d="M3 7v6h6" /><path strokeLinecap="round" strokeLinejoin="round" d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13" /></svg>
          </button>
          <button className="tb-btn" type="button" title="Redo (Cmd+Shift+Z / Ctrl+Y)" id="btn-redo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}><path strokeLinecap="round" strokeLinejoin="round" d="M21 7v6h-6" /><path strokeLinecap="round" strokeLinejoin="round" d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13" /></svg>
          </button>
          <button className="tb-btn" type="button" title="Delete Selected Part (Delete / Backspace)" id="btn-delete" style={{color: '#ef4444'}}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{width: 16, height: 16}}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
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
          <div className="hud-btn" id="hud-delete" title="Delete Selected Part (Delete / Backspace)"><span className="material-symbols-outlined" style={{fontSize: '18px', color: '#ef4444'}}>delete</span></div>
          <div className="hud-btn" id="hud-clear" title="Clear Entire Canvas"><span className="material-symbols-outlined" style={{fontSize: '18px', color: '#64748b'}}>delete_sweep</span></div>
        </div>
        {/* SVG Engine Engine */}
        <svg id="model-svg" width="100%" height="100%" style={{display: 'block'}} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }} onDrop={handleCanvasDrop}>
          <defs>
            <pattern id="dot-grid" width={20} height={20} patternUnits="userSpaceOnUse">
              <circle cx={2} cy={2} r={1} fill="rgba(100,116,139,0.25)" />
            </pattern>

            {/* Standard Arrow Markers */}
            <marker id="arrow-solid" markerWidth={10} markerHeight={10} refX={8} refY={5} orient="auto">
              <polygon points="1 2, 9 5, 1 8" fill="var(--color-text-primary, #1e293b)" />
            </marker>
            <marker id="arrow-solid-selected" markerWidth={10} markerHeight={10} refX={8} refY={5} orient="auto">
              <polygon points="1 2, 9 5, 1 8" fill="var(--color-accent, #6B4EE6)" />
            </marker>
            
            <marker id="arrow-open" markerWidth={10} markerHeight={10} refX={7} refY={5} orient="auto">
              <path d="M 2 2 L 8 5 L 2 8" fill="none" stroke="var(--color-text-primary, #1e293b)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </marker>
            <marker id="arrow-open-selected" markerWidth={10} markerHeight={10} refX={7} refY={5} orient="auto">
              <path d="M 2 2 L 8 5 L 2 8" fill="none" stroke="var(--color-accent, #6B4EE6)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </marker>

            <marker id="arrow-diamond" markerWidth={10} markerHeight={10} refX={5} refY={5} orient="auto">
              <polygon points="5 1.5, 8.5 5, 5 8.5, 1.5 5" fill="var(--color-text-primary, #1e293b)" />
            </marker>
            <marker id="arrow-diamond-selected" markerWidth={10} markerHeight={10} refX={5} refY={5} orient="auto">
              <polygon points="5 1.5, 8.5 5, 5 8.5, 1.5 5" fill="var(--color-accent, #6B4EE6)" />
            </marker>

            <marker id="arrow-circle" markerWidth={10} markerHeight={10} refX={5} refY={5} orient="auto">
              <circle cx={5} cy={5} r={3} fill="var(--color-text-primary, #1e293b)" />
            </marker>
            <marker id="arrow-circle-selected" markerWidth={10} markerHeight={10} refX={5} refY={5} orient="auto">
              <circle cx={5} cy={5} r={3} fill="var(--color-accent, #6B4EE6)" />
            </marker>

            {/* Aliases for arrowhead */}
            <marker id="arrowhead" markerWidth={10} markerHeight={7} refX={9} refY={3.5} orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-text-secondary)" style={{pointerEvents: 'none'}} />
            </marker>
            <marker id="arrowhead-selected" markerWidth={10} markerHeight={7} refX={9} refY={3.5} orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-accent)" style={{pointerEvents: 'none'}} />
            </marker>
            <marker
              id="arrow-solid"
              markerWidth={10}
              markerHeight={10}
              refX={8}
              refY={5}
              orient="auto"
            >
              <polygon points="1 2, 9 5, 1 8" fill="#1e293b" />
            </marker>

            <marker
              id="arrow-solid-selected"
              markerWidth={10}
              markerHeight={10}
              refX={8}
              refY={5}
              orient="auto"
            >
              <polygon
                points="1 2, 9 5, 1 8"
                fill="var(--color-accent)"
              />
            </marker>

            <marker
              id="arrow-open"
              markerWidth={10}
              markerHeight={10}
              refX={7}
              refY={5}
              orient="auto"
            >
              <path
                d="M 2 2 L 8 5 L 2 8"
                fill="none"
                stroke="#1e293b"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </marker>

            <marker
              id="arrow-open-selected"
              markerWidth={10}
              markerHeight={10}
              refX={7}
              refY={5}
              orient="auto"
            >
              <path
                d="M 2 2 L 8 5 L 2 8"
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </marker>

            <marker
              id="arrow-diamond"
              markerWidth={10}
              markerHeight={10}
              refX={5}
              refY={5}
              orient="auto"
            >
              <polygon
                points="5 1.5, 8.5 5, 5 8.5, 1.5 5"
                fill="#1e293b"
              />
            </marker>

            <marker
              id="arrow-diamond-selected"
              markerWidth={10}
              markerHeight={10}
              refX={5}
              refY={5}
              orient="auto"
            >
              <polygon
                points="5 1.5, 8.5 5, 5 8.5, 1.5 5"
                fill="var(--color-accent)"
              />
            </marker>
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
  <div id="view-results" className="view-panel" style={{ display: currentView === 'results' ? 'flex' : 'none', flex: 1, minHeight: 0, height: '100%', overflow: 'hidden' }}>
    {/* ═══ APP BODY ═══ */}
    <div className="app-body" style={{ flex: 1, height: '100%', minHeight: 0, display: 'flex', overflow: 'hidden' }}>
      {/* ─── Results Hierarchy Tree (Left) ─── */}
      <aside className="results-sidebar" id="results-sidebar">
        <div className="results-sidebar__search">
          <div className="results-sidebar__search-wrap">
            <svg className="results-sidebar__search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={11} cy={11} r={8} /><line x1={21} y1={21} x2="16.65" y2="16.65" /></svg>
            <input 
              type="text" 
              className="results-sidebar__search-input" 
              placeholder="Filter results... (⌘F)" 
              value={resultsSearchQuery}
              onChange={e => setResultsSearchQuery(e.target.value)}
            />
          </div>
        </div>
        <div className="results-sidebar__tree" id="results-tree">
          {/* Graphical output */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection?.(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Graphical output</span>
            </div>
            <div className="tree-section__items">
              <a href="#" className="tree-item" onClick={(e) => { e.preventDefault(); setCurrentView('model'); }}>Path model graph</a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Outer model loadings</a>
            </div>
          </div>
          {/* Final results */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection?.(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Final results</span>
            </div>
            <div className="tree-section__items">
              <a
                href="#"
                className={`tree-item ${
                  activeResultTab === 'path_coefficients' ? 'active' : ''
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveResultTab('path_coefficients');
                }}
              >
                <div className="tree-item__left">
                  <div className="tree-item__dot" />
                  <span>Path coefficients</span>
                </div>
                {resultConstructs.length > 0 && <span className="tree-item__size">{resultConstructs.length}×{resultConstructs.length}</span>}
              </a>
              <a
                href="#"
                className={`tree-item ${activeResultTab === 'total_effects' ? 'active' : ''}`}
                onClick={(e) => { e.preventDefault(); setActiveResultTab('total_effects'); }}
              >
                Total & indirect effects
              </a>
              <a
                href="#"
                className={`tree-item ${activeResultTab === 'outer_loadings' ? 'active' : ''}`}
                onClick={(e) => { e.preventDefault(); setActiveResultTab('outer_loadings'); }}
              >
                Outer loadings
              </a>
              <a
                href="#"
                className={`tree-item ${activeResultTab === 'outer_weights' ? 'active' : ''}`}
                onClick={(e) => { e.preventDefault(); setActiveResultTab('outer_weights'); }}
              >
                Outer weights
              </a>
              <a
                href="#"
                className={`tree-item ${activeResultTab === 'construct_scores' ? 'active' : ''}`}
                onClick={(e) => { e.preventDefault(); setActiveResultTab('construct_scores'); }}
              >
                Latent variable scores
              </a>
              <a
                href="#"
                className={`tree-item ${activeResultTab === 'bootstrap_significance' ? 'active' : ''}`}
                onClick={(e) => { e.preventDefault(); setActiveResultTab('bootstrap_significance'); }}
                style={{ position: 'relative' }}
              >
                <div className="tree-item__left">
                  <div className="tree-item__dot" style={{ backgroundColor: '#6366f1' }} />
                  <span>Bootstrap significance</span>
                </div>
                {plsResults?.significance && (
                  <span className="tree-item__size" style={{ backgroundColor: '#e0e7ff', color: '#4338ca', fontWeight: 600 }}>
                    p & t
                  </span>
                )}
              </a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Total indirect effects</a>
              <a href="#" className="tree-item tree-item--sub" onClick={(e) => e.preventDefault()}>Specific indirect effects</a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Total effects</a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Outer loadings</a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Outer weights</a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Latent variables</a>
              <a href="#" className="tree-item" onClick={(e) => e.preventDefault()}>Residuals</a>
            </div>
          </div>
          {/* Quality criteria */}
          <div className="tree-section">
            <div className="tree-section__header" onClick={(e) => { (window as any).toggleTreeSection?.(e.currentTarget); }}>
              <svg className="open" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              <span>Quality criteria</span>
            </div>
            <div className="tree-section__items">
              <a
                href="#"
                className={`tree-item ${
                  activeResultTab === 'r_squared' ? 'active' : ''
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveResultTab('r_squared');
                }}
              >
                R-square (R²)
              </a>

              <a
                href="#"
                className={`tree-item ${
                  activeResultTab === 'f_squared' ? 'active' : ''
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveResultTab('f_squared');
                }}
              >
                f-square (f²)
              </a>

              <a
                href="#"
                className={`tree-item ${
                  activeResultTab === 'reliability' ? 'active' : ''
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveResultTab('reliability');
                }}
              >
                Construct reliability & validity
              </a>

              <a
                href="#"
                className={`tree-item ${
                  activeResultTab === 'discriminant' ? 'active' : ''
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveResultTab('discriminant');
                }}
              >
                Discriminant validity
              </a>

              <a
                href="#"
                className={`tree-item ${
                  activeResultTab === 'collinearity' ? 'active' : ''
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  setActiveResultTab('collinearity');
                }}
              >
                Collinearity statistics (VIF)
              </a>
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
                {reportTabDetails.title}
                <span className="report-header__title-sub">{reportTabDetails.badge}</span>
              </h1>
              <p className="report-header__subtitle">{reportTabDetails.subtitle}</p>
            </div>
            {activeResultTab === 'path_coefficients' && (
              <div className="view-toggle">
                <div
                  className={`view-toggle__btn ${
                    resultViewMode === 'matrix' ? 'active' : ''
                  }`}
                  onClick={() => setResultViewMode('matrix')}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                  </svg>
                  Matrix View
                </div>

                <div
                  className={`view-toggle__btn ${
                    resultViewMode === 'list' ? 'active' : ''
                  }`}
                  onClick={() => setResultViewMode('list')}
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                  </svg>
                  List View
                </div>
              </div>
            )}
              </div>
            )}
          </div>
          <div className="report-filters">
            <div className="report-filters__left">
              {plsResults && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px',
                    fontSize: '13px',
                    color: '#475569'
                  }}
                >
                  <span>
                    Converged:{' '}
                    <strong style={{ color: '#16a34a' }}>
                      {plsResults.converged ? 'Yes' : 'No'}
                    </strong>
                  </span>

                  <span>
                    Iterations:{' '}
                    <strong>{plsResults.iterations}</strong>
                  </span>

                  <span>
                    Sample Size (N):{' '}
                    <strong>{plsResults.n_samples}</strong>
                  </span>
                </div>
              )}
            </div>

            <div className="report-filters__right">
              <button
                className="report-action-btn"
                type="button"
                onClick={handleCopyCurrentTable}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                </svg>
                Copy Table
              </button>

              <button
                className="report-action-btn"
                type="button"
                onClick={handleExportCurrentTable}
              >
                Export CSV
              </button>
            </div>
          </div>
        </div>

        {/* Table Area */}
        {resultsViewMode === 'matrix' ? (
          <div className="table-container">
            <div className="scientific-table-wrap">
              <table className="scientific-table">
                <colgroup>
                  <col style={{ width: 176 }} />
                  {CONSTRUCT_LIST.map(c => (
                    <col key={c.code} style={{ width: `${88 / CONSTRUCT_LIST.length}%` }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    <th>Construct</th>
                    {CONSTRUCT_LIST.map(c => (
                      <th key={c.code}>{c.code}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {CONSTRUCT_LIST.map(from => (
                    <tr key={from.code}>
                      <td>
                        <div className="construct-label">
                          <div className="construct-dot" style={{ background: from.color }} />
                          <span className="construct-name">{from.code}</span>
                          <span className="construct-role">({from.role})</span>
                        </div>
                      </td>
                      {CONSTRUCT_LIST.map(to => {
                        if (from.code === to.code) {
                          return <td key={to.code} className="cell-empty">—</td>;
                        }
                        const stat = getPathStat(from.code, to.code);
                        const isSig = stat.pValue < 0.05;
                        const sigClass = highlightSignificant && isSig
                          ? (stat.pValue < 0.001 ? 'cell-sig--very-strong' : (stat.pValue < 0.01 ? 'cell-sig--strong' : 'cell-sig'))
                          : (isSig ? '' : 'cell-ns');

                        return (
                          <td key={to.code} className={sigClass}>
                            <div className="cell-value">
                              {stat.beta.toFixed(3)}
                              {highlightSignificant && stat.stars && (
                                <span className="cell-stars">{stat.stars}</span>
                              )}
                            </div>
                            {showTStats && (
                              <div className="cell-stats">
                                t={stat.tStat.toFixed(3)} · {stat.pValue < 0.001 ? 'p<0.001' : `p=${stat.pValue.toFixed(3)}`}
                              </div>
                            )}
                          </td>
                        );
        {/* Dynamic Table Area */}
        <div className="table-container">
          <div className="scientific-table-wrap">
            {!plsResults ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>
                <svg style={{ width: 48, height: 48, margin: '0 auto 16px', color: '#94a3b8' }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                  <path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h3 style={{ margin: '0 0 8px', fontSize: '16px', fontWeight: 600, color: '#334155' }}>No Results Calculated Yet</h3>
                <p style={{ margin: 0, fontSize: '13px' }}>Return to the model canvas and click <strong>Calculate</strong> to run the PLS-SEM algorithm on your data.</p>
              </div>
            ) : activeResultTab === 'path_coefficients' ? (
              resultViewMode === 'matrix' ? (
                <table className="scientific-table">
                  <thead>
                    <tr>
                      <th>Source \ Target</th>
                      {resultConstructs.map(c => (
                        <th key={c}>{getConstructName(c)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {resultConstructs.map(sourceC => (
                      <tr key={sourceC}>
                        <td>
                          <div className="construct-label">
                            <div className="construct-dot" style={{ background: constructPalette[sourceC] || '#6366f1' }} />
                            <span className="construct-name">{getConstructName(sourceC)}</span>
                          </div>
                        </td>
                        {resultConstructs.map(targetC => {
                          const val = plsResults.structural?.path_coefficients?.[targetC]?.[sourceC];
                          if (val !== undefined && val !== null) {
                            return (
                              <td key={targetC} className="cell-sig">
                                <div className="cell-value">{fmt(val, 4)}</div>
                              </td>
                            );
                          }
                          return <td key={targetC} className="cell-empty">—</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <table className="scientific-table">
                  <thead>
                    <tr>
                      <th>Predictor (From)</th>
                      <th>Target (To)</th>
                      <th>Path Coefficient (β)</th>
                      <th>f² Effect Size</th>
                      <th>Inner VIF</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(plsResults.structural?.path_coefficients || {}).flatMap(([target, preds]: [string, any]) =>
                      Object.entries(preds || {}).map(([pred, val]: [string, any]) => {
                        const f2 = plsResults.structural?.f_squared?.[target]?.[pred];
                        const vif = plsResults.structural?.inner_vif?.[target]?.[pred];
                        return (
                          <tr key={`${pred}->${target}`}>
                            <td>
                              <div className="construct-label">
                                <div className="construct-dot" style={{ background: constructPalette[pred] || '#6366f1' }} />
                                <span className="construct-name">{getConstructName(pred)}</span>
                              </div>
                            </td>
                            <td>
                              <div className="construct-label">
                                <div className="construct-dot" style={{ background: constructPalette[target] || '#0ea5e9' }} />
                                <span className="construct-name">{getConstructName(target)}</span>
                              </div>
                            </td>
                            <td className="cell-sig">
                              <div className="cell-value">{fmt(val, 4)}</div>
                            </td>
                            <td>{f2 !== undefined ? fmt(f2, 4) : '—'}</td>
                            <td>{vif !== undefined ? fmt(vif, 4) : '1.0000'}</td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              )
            ) : activeResultTab === 'total_effects' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Source (From)</th>
                    <th>Target (To)</th>
                    <th>Direct Effect</th>
                    <th>Indirect Effect</th>
                    <th>Total Effect</th>
                  </tr>
                </thead>
                <tbody>
                  {(plsResults.structural?.effects || []).map((eff: any, idx: number) => (
                    <tr key={idx}>
                      <td>
                        <div className="construct-label">
                          <div className="construct-dot" style={{ background: constructPalette[eff.from] || '#6366f1' }} />
                          <span className="construct-name">{getConstructName(eff.from)}</span>
                        </div>
                      </td>
                      <td>
                        <div className="construct-label">
                          <div className="construct-dot" style={{ background: constructPalette[eff.to] || '#0ea5e9' }} />
                          <span className="construct-name">{getConstructName(eff.to)}</span>
                        </div>
                      </td>
                      <td>{fmt(eff.direct, 4)}</td>
                      <td>{fmt(eff.indirect, 4)}</td>
                      <td className="cell-sig">
                        <div className="cell-value">{fmt(eff.total, 4)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : activeResultTab === 'outer_loadings' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Construct</th>
                    <th>Indicator</th>
                    <th>Outer Loading (λ)</th>
                    <th>Indicator Reliability (λ²)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(plsResults.measurement?.outer_loadings || {}).flatMap(([cid, loads]: [string, any]) =>
                    Object.entries(loads || {}).map(([iid, val]: [string, any]) => {
                      const loadNum = Number(val);
                      const rel = plsResults.measurement?.indicator_reliability?.[cid]?.[iid] ?? (loadNum * loadNum);
                      const isHigh = loadNum >= 0.708;
                      return (
                        <tr key={`${cid}-${iid}`}>
                          <td>
                            <div className="construct-label">
                              <div className="construct-dot" style={{ background: constructPalette[cid] || '#6366f1' }} />
                              <span className="construct-name">{getConstructName(cid)}</span>
                            </div>
                          </td>
                          <td><strong>{getIndicatorName(iid)}</strong></td>
                          <td className={isHigh ? 'cell-sig' : 'cell-ns'}>
                            <div className="cell-value">{fmt(loadNum, 4)}</div>
                          </td>
                          <td>{fmt(rel, 4)}</td>
                          <td>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 600,
                              backgroundColor: isHigh ? '#dcfce7' : (loadNum >= 0.6 ? '#fef3c7' : '#fee2e2'),
                              color: isHigh ? '#166534' : (loadNum >= 0.6 ? '#92400e' : '#991b1b')
                            }}>
                              {isHigh ? 'Established (λ ≥ 0.708)' : (loadNum >= 0.6 ? 'Acceptable' : 'Low (< 0.60)')}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            ) : activeResultTab === 'outer_weights' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Construct</th>
                    <th>Indicator</th>
                    <th>Outer Weight (w)</th>
                    <th>Outer VIF</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(plsResults.measurement?.outer_weights || {}).flatMap(([cid, weights]: [string, any]) =>
                    Object.entries(weights || {}).map(([iid, val]: [string, any]) => {
                      const vif = plsResults.measurement?.outer_vif?.[cid]?.[iid];
                      return (
                        <tr key={`${cid}-${iid}`}>
                          <td>
                            <div className="construct-label">
                              <div className="construct-dot" style={{ background: constructPalette[cid] || '#6366f1' }} />
                              <span className="construct-name">{getConstructName(cid)}</span>
                            </div>
                          </td>
                          <td><strong>{getIndicatorName(iid)}</strong></td>
                          <td className="cell-sig">
                            <div className="cell-value">{fmt(val, 4)}</div>
                          </td>
                          <td>{vif !== undefined ? fmt(vif, 4) : '1.0000'}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            ) : activeResultTab === 'r_squared' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Endogenous Construct</th>
                    <th>R-Square (R²)</th>
                    <th>R-Square Adjusted</th>
                    <th>Variance Explained</th>
                    <th>Explanatory Power</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(plsResults.structural?.r_squared || {}).map(([cid, val]: [string, any]) => {
                    const r2 = Number(val);
                    const r2Adj = Number(plsResults.structural?.r_squared_adj?.[cid] ?? r2);
                    const power = r2 >= 0.67 ? 'Substantial' : (r2 >= 0.33 ? 'Moderate' : (r2 >= 0.19 ? 'Weak' : 'Very weak'));
                    return (
                      <tr key={cid}>
                        <td>
                          <div className="construct-label">
                            <div className="construct-dot" style={{ background: constructPalette[cid] || '#6366f1' }} />
                            <span className="construct-name">{getConstructName(cid)}</span>
                          </div>
                        </td>
                        <td className="cell-sig">
                          <div className="cell-value">{fmt(r2, 4)}</div>
                        </td>
                        <td>{fmt(r2Adj, 4)}</td>
                        <td>{(r2 * 100).toFixed(2)}%</td>
                        <td>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            fontWeight: 600,
                            backgroundColor: r2 >= 0.33 ? '#dcfce7' : '#fef3c7',
                            color: r2 >= 0.33 ? '#166534' : '#92400e'
                          }}>
                            {power}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : activeResultTab === 'f_squared' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Predictor (From)</th>
                    <th>Target (To)</th>
                    <th>f² Value</th>
                    <th>Effect Size Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(plsResults.structural?.f_squared || {}).flatMap(([target, preds]: [string, any]) =>
                    Object.entries(preds || {}).map(([pred, val]: [string, any]) => {
                      const f2 = Number(val);
                      const interp = f2 >= 0.35 ? 'Large effect (≥ 0.35)' : (f2 >= 0.15 ? 'Medium effect (≥ 0.15)' : (f2 >= 0.02 ? 'Small effect (≥ 0.02)' : 'Negligible (< 0.02)'));
                      return (
                        <tr key={`${pred}->${target}`}>
                          <td>
                            <div className="construct-label">
                              <div className="construct-dot" style={{ background: constructPalette[pred] || '#6366f1' }} />
                              <span className="construct-name">{getConstructName(pred)}</span>
                            </div>
                          </td>
                          <td>
                            <div className="construct-label">
                              <div className="construct-dot" style={{ background: constructPalette[target] || '#0ea5e9' }} />
                              <span className="construct-name">{getConstructName(target)}</span>
                            </div>
                          </td>
                          <td className="cell-sig">
                            <div className="cell-value">{fmt(f2, 4)}</div>
                          </td>
                          <td>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 600,
                              backgroundColor: f2 >= 0.15 ? '#dcfce7' : (f2 >= 0.02 ? '#fef3c7' : '#f1f5f9'),
                              color: f2 >= 0.15 ? '#166534' : (f2 >= 0.02 ? '#92400e' : '#475569')
                            }}>
                              {interp}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            ) : activeResultTab === 'reliability' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Construct</th>
                    <th>Cronbach's Alpha (α)</th>
                    <th>Composite Reliability (CR)</th>
                    <th>rho_A (ρA)</th>
                    <th>AVE</th>
                    <th>Evaluation</th>
                  </tr>
                </thead>
                <tbody>
                  {resultConstructs.map(cid => {
                    const rv = plsResults.reliability_and_validity || {};
                    const alpha = Number(rv.cronbachs_alpha?.[cid] ?? 0);
                    const cr = Number(rv.composite_reliability?.[cid] ?? 0);
                    const rhoA = Number(rv.rho_a?.[cid] ?? 0);
                    const ave = Number(rv.ave?.[cid] ?? 0);
                    const isGood = cr >= 0.7 && ave >= 0.5;
                    return (
                      <tr key={cid}>
                        <td>
                          <div className="construct-label">
                            <div className="construct-dot" style={{ background: constructPalette[cid] || '#6366f1' }} />
                            <span className="construct-name">{getConstructName(cid)}</span>
                          </div>
                        </td>
                        <td className={alpha >= 0.7 ? 'cell-sig' : 'cell-ns'}>{fmt(alpha, 4)}</td>
                        <td className={cr >= 0.7 ? 'cell-sig' : 'cell-ns'}>{fmt(cr, 4)}</td>
                        <td>{fmt(rhoA, 4)}</td>
                        <td className={ave >= 0.5 ? 'cell-sig' : 'cell-ns'}>{fmt(ave, 4)}</td>
                        <td>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            fontWeight: 600,
                            backgroundColor: isGood ? '#dcfce7' : '#fee2e2',
                            color: isGood ? '#166534' : '#991b1b'
                          }}>
                            {isGood ? 'Valid & Reliable (CR ≥ 0.7, AVE ≥ 0.5)' : 'Review Model'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : activeResultTab === 'discriminant' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
                <div>
                  <h4 style={{ margin: '0 0 8px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                    Heterotrait-Monotrait Ratio (HTMT)
                    <span style={{ marginLeft: '8px', fontSize: '11px', fontWeight: 400, color: '#64748b' }}>(Threshold &lt; 0.85 / 0.90)</span>
                  </h4>
                  <table className="scientific-table">
                    <thead>
                      <tr>
                        <th>Construct</th>
                        {resultConstructs.map(c => <th key={c}>{getConstructName(c)}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {resultConstructs.map(c1 => (
                        <tr key={c1}>
                          <td>
                            <div className="construct-label">
                              <div className="construct-dot" style={{ background: constructPalette[c1] || '#6366f1' }} />
                              <span className="construct-name">{getConstructName(c1)}</span>
                            </div>
                          </td>
                          {resultConstructs.map(c2 => {
                            if (c1 === c2) return <td key={c2} className="cell-empty">—</td>;
                            const htmtVal = plsResults.reliability_and_validity?.htmt?.[c1]?.[c2];
                            if (htmtVal !== undefined) {
                              const num = Number(htmtVal);
                              const ok = num < 0.85;
                              return (
                                <td key={c2} className={ok ? 'cell-sig' : 'cell-ns'}>
                                  <div className="cell-value">{fmt(num, 4)}</div>
                                </td>
                              );
                            }
                            return <td key={c2} className="cell-empty">—</td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div>
                  <h4 style={{ margin: '0 0 8px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                    Fornell-Larcker Criterion
                    <span style={{ marginLeft: '8px', fontSize: '11px', fontWeight: 400, color: '#64748b' }}>(Diagonal: √AVE, Off-diagonal: construct correlations)</span>
                  </h4>
                  <table className="scientific-table">
                    <thead>
                      <tr>
                        <th>Construct</th>
                        {resultConstructs.map(c => <th key={c}>{getConstructName(c)}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {resultConstructs.map(c1 => (
                        <tr key={c1}>
                          <td>
                            <div className="construct-label">
                              <div className="construct-dot" style={{ background: constructPalette[c1] || '#6366f1' }} />
                              <span className="construct-name">{getConstructName(c1)}</span>
                            </div>
                          </td>
                          {resultConstructs.map(c2 => {
                            const flVal = plsResults.reliability_and_validity?.fornell_larcker?.[c1]?.[c2];
                            if (flVal !== undefined) {
                              const isDiag = c1 === c2;
                              return (
                                <td key={c2} style={isDiag ? { backgroundColor: '#f1f5f9', fontWeight: 700 } : {}}>
                                  <div>{fmt(flVal, 4)}</div>
                                </td>
                              );
                            }
                            return <td key={c2} className="cell-empty">—</td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : activeResultTab === 'collinearity' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
                <div>
                  <h4 style={{ margin: '0 0 8px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>Inner Model VIF (Predictors of Endogenous Constructs)</h4>
                  <table className="scientific-table">
                    <thead>
                      <tr>
                        <th>Target Construct</th>
                        <th>Predictor Construct</th>
                        <th>Inner VIF</th>
                        <th>Collinearity Evaluation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(plsResults.structural?.inner_vif || {}).flatMap(([target, preds]: [string, any]) =>
                        Object.entries(preds || {}).map(([pred, val]: [string, any]) => {
                          const vif = Number(val);
                          const ok = vif < 3.3;
                          return (
                            <tr key={`${pred}->${target}`}>
                              <td><strong>{getConstructName(target)}</strong></td>
                              <td>{getConstructName(pred)}</td>
                              <td className={ok ? 'cell-sig' : 'cell-ns'}>{fmt(vif, 4)}</td>
                              <td>
                                <span style={{
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  backgroundColor: ok ? '#dcfce7' : '#fee2e2',
                                  color: ok ? '#166534' : '#991b1b'
                                }}>
                                  {ok ? 'No Collinearity Issue (VIF < 3.3)' : 'Potential Multicollinearity (VIF ≥ 3.3)'}
                                </span>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>

                <div>
                  <h4 style={{ margin: '0 0 8px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>Outer Model VIF (Indicators)</h4>
                  <table className="scientific-table">
                    <thead>
                      <tr>
                        <th>Construct</th>
                        <th>Indicator</th>
                        <th>Outer VIF</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(plsResults.measurement?.outer_vif || {}).flatMap(([cid, vifs]: [string, any]) =>
                        Object.entries(vifs || {}).map(([iid, val]: [string, any]) => (
                          <tr key={`${cid}-${iid}`}>
                            <td>{getConstructName(cid)}</td>
                            <td><strong>{getIndicatorName(iid)}</strong></td>
                            <td>{fmt(val, 4)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : activeResultTab === 'construct_scores' ? (
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th>Observation #</th>
                    {resultConstructs.map(c => <th key={c}>{getConstructName(c)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: Math.min(25, (plsResults.construct_scores?.[resultConstructs[0]] || []).length) }).map((_, rIdx) => (
                    <tr key={rIdx}>
                      <td><strong>Case #{rIdx + 1}</strong></td>
                      {resultConstructs.map(c => {
                        const val = plsResults.construct_scores?.[c]?.[rIdx];
                        return <td key={c}>{fmt(val, 4)}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="sig-legend">
                <span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Significance Legend:</span>
                <div className="sig-legend__item"><span className="sig-legend__stars">*</span> p &lt; 0.05</div>
                <div className="sig-legend__item"><span className="sig-legend__stars">**</span> p &lt; 0.01</div>
                <div className="sig-legend__item"><span className="sig-legend__stars">***</span> p &lt; 0.001</div>
                <span style={{ flex: 1 }} />
                <div style={{ fontFamily: 'var(--font-sans)' }}>Based on 5000 bootstrap subsamples</div>
              </div>
            </div>
            ) : activeResultTab === 'bootstrap_significance' ? (
              !plsResults.significance ? (
                <div style={{ padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>
                  <svg style={{ width: 48, height: 48, margin: '0 auto 16px', color: '#94a3b8' }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                    <path d="M18 20V10M12 20V4M6 20v-6" />
                  </svg>
                  <h3 style={{ margin: '0 0 8px', fontSize: '16px', fontWeight: 600, color: '#334155' }}>No Bootstrapping Run Yet</h3>
                  <p style={{ margin: 0, fontSize: '13px' }}>Click the <strong>Bootstrap</strong> button in the top bar to run multi-core significance testing for standard errors, t-statistics, and p-values.</p>
                </div>
              ) : (
                <div>
                  {/* Summary Bar */}
                  <div style={{
                    display: 'flex',
                    gap: '20px',
                    padding: '14px 18px',
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    marginBottom: '20px',
                    alignItems: 'center',
                    fontSize: '13px',
                    color: '#334155',
                  }}>
                    <span>Bootstrap Samples: <strong>{plsResults.significance.n_boot?.toLocaleString()}</strong></span>
                    <span>Test: <strong>Two-Tailed (α = 0.05)</strong></span>
                    <span>Confidence Interval: <strong>95% Percentile</strong></span>
                    <span style={{ marginLeft: 'auto', fontSize: '12px', color: '#64748b' }}>
                      Significance: *** p &lt; 0.001, ** p &lt; 0.01, * p &lt; 0.05, ns not significant
                    </span>
                  </div>

                  {/* Path Coefficients Significance Table */}
                  <h4 style={{ margin: '0 0 10px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                    Structural Path Significance
                  </h4>
                  <table className="scientific-table" style={{ marginBottom: '32px' }}>
                    <thead>
                      <tr>
                        <th>Path (Predictor → Target)</th>
                        <th>Original (β)</th>
                        <th>Sample Mean</th>
                        <th>Std Error (SE)</th>
                        <th>t-Statistic</th>
                        <th>p-Value</th>
                        <th>95% Confidence Interval</th>
                        <th>Significance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(plsResults.significance.paths || []).map((p: any, idx: number) => {
                        const isSig = p.p_value < 0.05;
                        return (
                          <tr key={idx}>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span className="construct-name">{p.from_name || getConstructName(p.from)}</span>
                                <span style={{ color: '#94a3b8' }}>→</span>
                                <span className="construct-name">{p.to_name || getConstructName(p.to)}</span>
                              </div>
                            </td>
                            <td className="cell-sig">
                              <div className="cell-value">{fmt(p.original, 4)}</div>
                            </td>
                            <td>{fmt(p.mean, 4)}</td>
                            <td>{fmt(p.se, 4)}</td>
                            <td><strong>{fmt(p.t_stat, 3)}</strong></td>
                            <td style={{ color: isSig ? '#15803d' : '#b45309', fontWeight: 600 }}>
                              {p.p_value < 0.0001 ? '< 0.0001' : fmt(p.p_value, 4)}
                            </td>
                            <td>[{fmt(p.ci_low, 4)}, {fmt(p.ci_high, 4)}]</td>
                            <td>
                              <span style={{
                                padding: '2px 8px',
                                borderRadius: '4px',
                                fontSize: '12px',
                                fontWeight: 600,
                                backgroundColor: isSig ? '#dcfce7' : '#f1f5f9',
                                color: isSig ? '#166534' : '#64748b',
                              }}>
                                {p.significance}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>

                  {/* Outer Loadings Significance Table */}
                  <h4 style={{ margin: '0 0 10px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                    Outer Loadings Significance
                  </h4>
                  <table className="scientific-table">
                    <thead>
                      <tr>
                        <th>Construct</th>
                        <th>Indicator</th>
                        <th>Outer Loading (λ)</th>
                        <th>Sample Mean</th>
                        <th>Std Error (SE)</th>
                        <th>t-Statistic</th>
                        <th>p-Value</th>
                        <th>95% Confidence Interval</th>
                        <th>Sig.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(plsResults.significance.loadings || []).map((l: any, idx: number) => {
                        const isSig = l.p_value < 0.05;
                        return (
                          <tr key={idx}>
                            <td>{l.construct_name || getConstructName(l.construct)}</td>
                            <td><strong>{l.indicator_name || getIndicatorName(l.indicator)}</strong></td>
                            <td className="cell-sig">
                              <div className="cell-value">{fmt(l.original, 4)}</div>
                            </td>
                            <td>{fmt(l.mean, 4)}</td>
                            <td>{fmt(l.se, 4)}</td>
                            <td>{fmt(l.t_stat, 3)}</td>
                            <td style={{ color: isSig ? '#15803d' : '#b45309', fontWeight: 600 }}>
                              {l.p_value < 0.0001 ? '< 0.0001' : fmt(l.p_value, 4)}
                            </td>
                            <td>[{fmt(l.ci_low, 4)}, {fmt(l.ci_high, 4)}]</td>
                            <td>
                              <span style={{
                                padding: '2px 8px',
                                borderRadius: '4px',
                                fontSize: '11px',
                                fontWeight: 600,
                                backgroundColor: isSig ? '#dcfce7' : '#f1f5f9',
                                color: isSig ? '#166534' : '#64748b',
                              }}>
                                {l.significance}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )
            ) : null}

            {plsResults && (
              <div className="sig-legend">
                <span style={{color: 'var(--color-text-secondary)', fontWeight: 500}}>Status:</span>
                <div className="sig-legend__item"><span style={{color: '#10b981'}}>✓</span> Converged: {plsResults.converged ? 'Yes' : 'No'}</div>
                <div className="sig-legend__item"><span style={{color: '#6366f1'}}>ℹ</span> Iterations: {plsResults.iterations}</div>
                <div className="sig-legend__item"><span style={{color: '#0ea5e9'}}>N:</span> {plsResults.n_samples} cases</div>
                <span style={{flex: 1}} />
                <div style={{fontFamily: 'var(--font-sans)', fontSize: '12px', color: '#64748b'}}>PLS-SEM Engine · Path Weighting Scheme</div>
              </div>
            )}
          </div>
        ) : (
          <div className="table-container">
            <div className="scientific-table-wrap">
              <table className="scientific-table">
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', paddingLeft: '16px' }}>Path</th>
                    <th style={{ textAlign: 'right' }}>Original Sample (β)</th>
                    <th style={{ textAlign: 'right' }}>Sample Mean (M)</th>
                    <th style={{ textAlign: 'right' }}>Standard Deviation (STDEV)</th>
                    <th style={{ textAlign: 'right' }}>T Statistics (|O/STDEV|)</th>
                    <th style={{ textAlign: 'right' }}>P Values</th>
                    <th style={{ textAlign: 'center' }}>Significance</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPaths.map((p) => {
                    const isSig = p.pValue < 0.05;
                    return (
                      <tr key={`${p.from}->${p.to}`} style={{ borderBottom: '1px solid #F1F5F9' }}>
                        <td style={{ padding: '8px 16px', fontWeight: 600 }}>
                          <span style={{ color: '#6B4EE6' }}>{p.from}</span>
                          <span style={{ margin: '0 8px', color: '#94A3B8' }}>→</span>
                          <span style={{ color: '#0F172A' }}>{p.to}</span>
                        </td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{p.beta.toFixed(3)}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', color: '#64748B' }}>{p.mean.toFixed(3)}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', color: '#64748B' }}>{p.stdev.toFixed(3)}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', color: '#0F172A', fontWeight: 500 }}>{p.tStat.toFixed(3)}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', color: isSig && highlightSignificant ? '#059669' : '#0F172A', fontWeight: isSig && highlightSignificant ? 600 : 400 }}>
                          {p.pValue < 0.001 ? '< 0.001' : p.pValue.toFixed(3)}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          {isSig && highlightSignificant ? (
                            <span style={{ 
                              fontSize: '11px', 
                              fontWeight: 600, 
                              color: '#059669', 
                              backgroundColor: '#ECFDF5', 
                              border: '1px solid #A7F3D0',
                              padding: '2px 8px', 
                              borderRadius: '12px' 
                            }}>
                              Significant {p.stars}
                            </span>
                          ) : (
                            <span style={{ fontSize: '11px', color: '#94A3B8', backgroundColor: '#F8FAFC', padding: '2px 8px', borderRadius: '12px' }}>
                              ns
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="sig-legend">
                <span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>Significance Legend:</span>
                <div className="sig-legend__item"><span className="sig-legend__stars">*</span> p &lt; 0.05</div>
                <div className="sig-legend__item"><span className="sig-legend__stars">**</span> p &lt; 0.01</div>
                <div className="sig-legend__item"><span className="sig-legend__stars">***</span> p &lt; 0.001</div>
                <span style={{ flex: 1 }} />
                <div style={{ fontFamily: 'var(--font-sans)' }}>Based on 5000 bootstrap subsamples</div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>{/* /app-body */}
  </div>{/* /view-results */}
  {datasetToImport && (
    <DataManagerModal
      dataset={datasetToImport}
      onImport={handleImportComplete}
      onCancel={() => setDatasetToImport(null)}
    />
  )}

  <BootstrapModal
    isOpen={isBootstrapModalOpen}
    projectPath={activeStudy?.path || ''}
    spec={exportModelSpec()}
    datasetHeaders={activeDataset?.variables?.map(v => v.name)}
    datasetRows={activeDataset?.rows}
    datasetName={activeDataset?.filename}
    onComplete={(results) => {
      setPlsResults(results);
      setActiveResultTab('bootstrap_significance');
      const viewSlider = document.getElementById('main-view-slider');
      if (viewSlider) {
        (viewSlider as HTMLElement).style.display = 'flex';
      }
      switchView('results');
      setValidationSuccessToast('Bootstrapping complete! Results updated.');
      setTimeout(() => setValidationSuccessToast(null), 3500);
    }}
    onClose={() => setIsBootstrapModalOpen(false)}
  />

  {/* ─── Validation Error Modal ─── */}
  {validationModal && (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(15, 23, 42, 0.65)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
    }}>
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        width: '480px',
        maxWidth: '90vw',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        overflow: 'hidden',
        border: '1px solid #e2e8f0',
      }}>
        <div style={{
          padding: '18px 20px',
          borderBottom: '1px solid #f1f5f9',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          backgroundColor: '#fff1f2',
        }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '8px',
            backgroundColor: '#ffe4e6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#e11d48',
            flexShrink: 0,
          }}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#9f1239' }}>Model Validation Issues</h3>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#be123c' }}>Please fix the following issues before running analysis:</p>
          </div>
        </div>
        
        <div style={{ padding: '16px 20px', maxHeight: '340px', overflowY: 'auto' }}>
          {validationModal.errors && validationModal.errors.length > 0 && (
            <div style={{ marginBottom: '14px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#e11d48', marginBottom: '8px', letterSpacing: '0.05em' }}>
                Errors ({validationModal.errors.length})
              </div>
              <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {validationModal.errors.map((err, idx) => (
                  <li key={idx} style={{ fontSize: '13px', color: '#334155', lineHeight: '1.4' }}>
                    {err}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {validationModal.warnings && validationModal.warnings.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#d97706', marginBottom: '8px', letterSpacing: '0.05em' }}>
                Warnings ({validationModal.warnings.length})
              </div>
              <ul style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {validationModal.warnings.map((warn, idx) => (
                  <li key={idx} style={{ fontSize: '13px', color: '#64748b', lineHeight: '1.4' }}>
                    {warn}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div style={{
          padding: '12px 20px',
          backgroundColor: '#f8fafc',
          borderTop: '1px solid #f1f5f9',
          display: 'flex',
          justifyContent: 'flex-end',
        }}>
          <button
            type="button"
            onClick={() => setValidationModal(null)}
            style={{
              padding: '8px 16px',
              backgroundColor: '#0f172a',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Back to Canvas
          </button>
        </div>
      </div>
    </div>
  )}

  {/* ─── Toast Notifications ─── */}
  {saveToast && (
    <div style={{
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      backgroundColor: '#0f172a',
      color: '#ffffff',
      padding: '10px 18px',
      borderRadius: '8px',
      fontSize: '13px',
      fontWeight: 500,
      boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      zIndex: 9999,
    }}>
      <span style={{ color: '#10b981' }}>✓</span> {saveToast}
    </div>
  )}
  {validationSuccessToast && (
    <div style={{
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      backgroundColor: '#065f46',
      color: '#ffffff',
      padding: '10px 18px',
      borderRadius: '8px',
      fontSize: '13px',
      fontWeight: 500,
      boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      zIndex: 9999,
    }}>
      <span style={{ color: '#34d399' }}>✓</span> {validationSuccessToast}
    </div>
  )}

    </div>
  );
};

export default ModelEditor;
