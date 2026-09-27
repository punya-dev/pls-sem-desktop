import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ParsedDataset } from './utils/dataset-parser';

export type ShapeType = 'circle' | 'rect' | 'hexagon' | 'octagon';

export interface Workspace {
  id: string;
  name: string;
  path: string;
  archivedAt?: string;
  createdAt?: string;
  modifiedAt?: string;
}

export interface Model {
  id: string;
  studyId: string;
  name: string;
  type: string;
  lastModified: string;
}

export interface Study {
  id: string;
  workspaceId: string;
  name: string;
  type: string;
  description: string;
  lastModified: string;
  path: string;
  createdAt?: string;
}

export interface Variable {
  id: string;
  name: string;
  category: string;
  type: string;
}

export interface NodeData {
  id: string;
  label: string;
  x: number;
  y: number;
  isLatent: boolean;
  shape?: ShapeType;
  isText?: boolean;
  parentId?: string; // For indicators
  // Formatting
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  fontSize?: number;
  width?: number; // Custom sizing
  height?: number; // Custom sizing
  radius?: number; // Custom sizing
  fillColor?: string; // Custom color
}

export interface EdgeData {
  id: string;
  sourceId: string;
  targetId: string;
}
export interface ContextMenuItem {
  id: string;
  label: string;
  icon: string;
  danger?: boolean;
  action: () => void;
}

export interface AppSettings {
  version: string;
  websiteUrl: string;
  theme: 'light' | 'dark' | 'system';
  darkVariant: 'default' | 'grayscale' | 'true-black';
  fontFamily: 'Inter' | 'Roboto' | 'JetBrains Mono' | 'System';
  language: 'en' | 'es' | 'de' | 'fr' | 'zh';
  decimalSystem: 'point' | 'comma';
  decimalDigits: number;
  parallelProcessors: number | 'all';
  keyboardLayout: 'qwerty' | 'azerty' | 'qwertz';
  flipOrientation: boolean;
  accentColor: string;
}

export interface DeleteConfirmDialog {
  title?: string;
  message?: string;
  itemName?: string;
  onConfirm: () => void;
}

export interface AppTab {
  id: string;
  type: 'get-started' | 'workspace' | 'model' | 'archive' | 'dataset' | 'docs' | 'samples' | 'feedback' | 'changelog';
  title: string;
  workspaceId?: string | null;
  studyId?: string | null;
  modelId?: string | null;
}

interface AppState {
  // Global & Settings
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  settings: AppSettings;
  updateSettings: (partial: Partial<AppSettings>) => void;
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  isSidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Deletion Confirmation Modal
  deleteConfirmation: DeleteConfirmDialog | null;
  requestDelete: (config: DeleteConfirmDialog) => void;
  closeDeleteConfirm: () => void;
  
  // Tabs (VSCode / Chrome Browser style)
  tabs: AppTab[];
  activeTabId: string;
  openTab: (tab: Omit<AppTab, 'id'> & { id?: string }) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  updateTabTitle: (id: string, title: string) => void;
  reorderTabs: (fromIndex: number, toIndex: number) => void;

  // Workspaces & Studies
  workspaces: Workspace[];
  archivedWorkspaces: Workspace[];
  activeWorkspaceId: string | null;
  studies: Study[];
  activeStudyId: string | null;
  models: Model[];
  datasetsByStudy: Record<string, ParsedDataset>;
  activeModelId: string | null;
  addModel: (model: Model) => void;
  removeModel: (id: string) => void;
  renameModel: (id: string, name: string) => void;
  duplicateModel: (id: string) => void;
  setActiveModel: (id: string) => void;

  addWorkspace: (ws: Workspace) => void;
  removeWorkspace: (id: string) => void;
  archiveWorkspace: (id: string) => void;
  restoreWorkspace: (id: string) => void;
  deleteWorkspace: (id: string) => void;
  deleteStudy: (id: string) => void;
  deleteModel: (id: string) => void;
  deleteDataset: (studyId: string) => void;
  renameWorkspace: (id: string, name: string) => void;
  setActiveWorkspace: (id: string) => void;
  addStudy: (study: Study) => void;
  syncWorkspaceStudies: (workspaceId: string, diskProjects: Array<{ path: string; name: string; fullPath: string }>) => void;
  removeStudy: (id: string) => void;
  renameStudy: (id: string, name: string) => void;
  duplicateStudy: (id: string) => void;
  setActiveStudy: (id: string) => void;
  setStudyDataset: (studyId: string, dataset: ParsedDataset) => void;
  removeStudyDataset: (studyId: string) => void;
  touchStudy: (id: string) => void;
  
  // Variables (Sidebar)
  variables: Variable[];
  
  // Canvas State
  nodes: NodeData[];
  edges: EdgeData[];
  selectedIds: Set<string>;
  mode: 'select' | 'latent' | 'connect' | 'moderation' | 'quadratic' | 'copula' | 'text';
  zoom: number;
  pan: { x: number, y: number };
  
  // Canvas Actions
  addNode: (node: NodeData) => void;
  updateNode: (id: string, data: Partial<NodeData>) => void;
  removeNodes: (ids: string[]) => void;
  addEdge: (sourceId: string, targetId: string) => void;
  removeEdges: (ids: string[]) => void;
  setMode: (mode: AppState['mode']) => void;
  setSelection: (ids: string[]) => void;
  clearSelection: () => void;
  setZoom: (zoom: number) => void;
  setPan: (x: number, y: number) => void;

  // Context Menu
  contextMenu: { x: number; y: number; items: ContextMenuItem[] } | null;
  openContextMenu: (x: number, y: number, items: ContextMenuItem[]) => void;
  closeContextMenu: () => void;
}

// Initial Mock Data removed in favor of empty starts
const INITIAL_WORKSPACES: Workspace[] = [];
const INITIAL_STUDIES: Study[] = [];
const INITIAL_MODELS: Model[] = [];
const INITIAL_VARIABLES: Variable[] = [
  { id: 'v1', name: 'QUAL_1', category: 'QUAL', type: 'ORD' },
  { id: 'v2', name: 'QUAL_2', category: 'QUAL', type: 'ORD' },
  { id: 'v3', name: 'QUAL_3', category: 'QUAL', type: 'ORD' },
  { id: 'v4', name: 'PERF_1', category: 'PERF', type: 'ORD' },
  { id: 'v5', name: 'PERF_2', category: 'PERF', type: 'ORD' },
  { id: 'v6', name: 'COMP_1', category: 'COMP', type: 'ORD' },
  { id: 'v7', name: 'COMP_2', category: 'COMP', type: 'ORD' },
  { id: 'v8', name: 'CSOR_1', category: 'CSOR', type: 'ORD' },
  { id: 'v9', name: 'CUSA_1', category: 'CUSA', type: 'ORD' },
];

const INITIAL_SETTINGS: AppSettings = {
  version: '0.1.0',
  websiteUrl: 'https://cspls.org',
  theme: 'light',
  darkVariant: 'default',
  fontFamily: 'Inter',
  language: 'en',
  decimalSystem: 'point',
  decimalDigits: 3,
  parallelProcessors: 'all',
  keyboardLayout: 'qwerty',
  flipOrientation: false,
  accentColor: '#6B4EE6',
};

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      // Global & Settings
      theme: 'light',
      toggleTheme: () => set((state) => {
        const nextTheme: 'light' | 'dark' = state.theme === 'light' ? 'dark' : 'light';
        return {
          theme: nextTheme,
          settings: { ...state.settings, theme: nextTheme },
        };
      }),
      settings: INITIAL_SETTINGS,
      updateSettings: (partial) => set((state) => {
        let nextTheme = state.theme;
        if (partial.theme) {
          nextTheme = partial.theme === 'dark' ? 'dark' : 'light';
        }
        return {
          settings: { ...state.settings, ...partial },
          theme: nextTheme,
        };
      }),
      isSettingsOpen: false,
      setIsSettingsOpen: (open) => set({ isSettingsOpen: open }),
      isSidebarCollapsed: false,
      toggleSidebar: () => set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ isSidebarCollapsed: collapsed }),

      // Deletion Confirmation Modal
      deleteConfirmation: null,
      requestDelete: (config) => set({ deleteConfirmation: config }),
      closeDeleteConfirm: () => set({ deleteConfirmation: null }),
      
      // Tabs (VSCode / Chrome Browser style)
      tabs: [{ id: 'get-started', type: 'get-started', title: 'Home' }],
      activeTabId: 'get-started',
      openTab: (tabInput) => set((state) => {
        const SINGLETON_TYPES = ['get-started', 'archive', 'docs', 'samples', 'feedback', 'changelog'] as const;
        if (SINGLETON_TYPES.includes(tabInput.type as any)) {
          const existing = state.tabs.find(t => t.type === tabInput.type);
          if (existing) {
            return { activeTabId: existing.id };
          }
          const id = tabInput.id || `tab-${tabInput.type}`;
          const title = tabInput.title || (
            tabInput.type === 'get-started' ? 'Home' :
            tabInput.type === 'archive' ? 'Archive' :
            tabInput.type === 'docs' ? 'Documentation' :
            tabInput.type === 'samples' ? 'Sample Projects' :
            tabInput.type === 'feedback' ? 'Feedback & Reports' :
            'Changelog'
          );
          const newTab: AppTab = { ...tabInput, id, title };
          return { tabs: [...state.tabs, newTab], activeTabId: id };
        }
        
        if (tabInput.type === 'workspace' && tabInput.workspaceId) {
          const existing = state.tabs.find(t => t.type === 'workspace' && t.workspaceId === tabInput.workspaceId);
          if (existing) {
            return { activeTabId: existing.id, activeWorkspaceId: tabInput.workspaceId };
          }
          const id = tabInput.id || `tab-ws-${tabInput.workspaceId}`;
          const newTab: AppTab = {
            id,
            type: 'workspace',
            title: tabInput.title || 'Workspace',
            workspaceId: tabInput.workspaceId,
          };
          return {
            tabs: [...state.tabs, newTab],
            activeTabId: id,
            activeWorkspaceId: tabInput.workspaceId,
          };
        }

        if (tabInput.type === 'model' && tabInput.modelId) {
          const existing = state.tabs.find(t => t.type === 'model' && t.modelId === tabInput.modelId);
          if (existing) {
            return {
              activeTabId: existing.id,
              activeModelId: tabInput.modelId,
              activeStudyId: tabInput.studyId ?? state.activeStudyId,
              activeWorkspaceId: tabInput.workspaceId ?? state.activeWorkspaceId,
            };
          }
          const id = tabInput.id || `tab-model-${tabInput.modelId}`;
          const newTab: AppTab = {
            id,
            type: 'model',
            title: tabInput.title || 'Model',
            workspaceId: tabInput.workspaceId,
            studyId: tabInput.studyId,
            modelId: tabInput.modelId,
          };
          return {
            tabs: [...state.tabs, newTab],
            activeTabId: id,
            activeModelId: tabInput.modelId,
            activeStudyId: tabInput.studyId ?? state.activeStudyId,
            activeWorkspaceId: tabInput.workspaceId ?? state.activeWorkspaceId,
          };
        }

        if (tabInput.type === 'dataset' && tabInput.studyId) {
          const existing = state.tabs.find(t => t.type === 'dataset' && t.studyId === tabInput.studyId);
          if (existing) {
            return {
              activeTabId: existing.id,
              activeStudyId: tabInput.studyId,
              activeWorkspaceId: tabInput.workspaceId ?? state.activeWorkspaceId,
            };
          }
          const id = tabInput.id || `tab-dataset-${tabInput.studyId}`;
          const newTab: AppTab = {
            id,
            type: 'dataset',
            title: tabInput.title || 'Dataset',
            workspaceId: tabInput.workspaceId,
            studyId: tabInput.studyId,
          };
          return {
            tabs: [...state.tabs, newTab],
            activeTabId: id,
            activeStudyId: tabInput.studyId,
            activeWorkspaceId: tabInput.workspaceId ?? state.activeWorkspaceId,
          };
        }

        const id = tabInput.id || `tab-${Date.now()}`;
        const newTab: AppTab = { ...tabInput, id };
        return { tabs: [...state.tabs, newTab], activeTabId: id };
      }),
      closeTab: (id) => set((state) => {
        const index = state.tabs.findIndex(t => t.id === id);
        if (index === -1) return state;

        const newTabs = state.tabs.filter(t => t.id !== id);
        if (newTabs.length === 0) {
          const homeTab: AppTab = { id: 'get-started', type: 'get-started', title: 'Home' };
          return { tabs: [homeTab], activeTabId: 'get-started' };
        }

        let nextActiveId = state.activeTabId;
        let nextWsId = state.activeWorkspaceId;
        let nextStudyId = state.activeStudyId;
        let nextModelId = state.activeModelId;

        if (state.activeTabId === id) {
          const nextTab = newTabs[Math.max(0, Math.min(index, newTabs.length - 1))];
          nextActiveId = nextTab.id;
          if (nextTab.type === 'workspace' && nextTab.workspaceId) {
            nextWsId = nextTab.workspaceId;
          } else if (nextTab.type === 'model') {
            nextModelId = nextTab.modelId ?? null;
            nextStudyId = nextTab.studyId ?? null;
            nextWsId = nextTab.workspaceId ?? null;
          } else if (nextTab.type === 'dataset') {
            nextStudyId = nextTab.studyId ?? null;
            nextWsId = nextTab.workspaceId ?? null;
          }
        }

        return {
          tabs: newTabs,
          activeTabId: nextActiveId,
          activeWorkspaceId: nextWsId,
          activeStudyId: nextStudyId,
          activeModelId: nextModelId,
        };
      }),
      setActiveTab: (id) => set((state) => {
        const tab = state.tabs.find(t => t.id === id);
        if (!tab) return state;
        let nextWs = state.activeWorkspaceId;
        let nextStudy = state.activeStudyId;
        let nextModel = state.activeModelId;
        if (tab.type === 'workspace' && tab.workspaceId) {
          nextWs = tab.workspaceId;
        } else if (tab.type === 'model') {
          if (tab.workspaceId) nextWs = tab.workspaceId;
          if (tab.studyId) nextStudy = tab.studyId;
          if (tab.modelId) nextModel = tab.modelId;
        } else if (tab.type === 'dataset') {
          if (tab.workspaceId) nextWs = tab.workspaceId;
          if (tab.studyId) nextStudy = tab.studyId;
        }
        return {
          activeTabId: id,
          activeWorkspaceId: nextWs,
          activeStudyId: nextStudy,
          activeModelId: nextModel,
        };
      }),
      updateTabTitle: (id, title) => set((state) => ({
        tabs: state.tabs.map(t => t.id === id ? { ...t, title } : t)
      })),
      reorderTabs: (fromIndex, toIndex) => set((state) => {
        const tabs = [...state.tabs];
        const [moved] = tabs.splice(fromIndex, 1);
        tabs.splice(toIndex, 0, moved);
        return { tabs };
      }),

      // Workspaces & Studies
      workspaces: INITIAL_WORKSPACES,
      archivedWorkspaces: [],
      activeWorkspaceId: null,
      studies: INITIAL_STUDIES,
      activeStudyId: null,
      models: INITIAL_MODELS,
      datasetsByStudy: {},
      activeModelId: null,
      addModel: (model) => set((state) => ({ models: [...state.models, model] })),
      removeModel: (id) => set((state) => ({ models: state.models.filter(model => model.id !== id) })),
      renameModel: (id, name) => set((state) => ({
        models: state.models.map(model => model.id === id ? { ...model, name, lastModified: 'Just now' } : model),
        tabs: state.tabs.map(tab => tab.type === 'model' && tab.modelId === id ? { ...tab, title: name } : tab),
      })),
      duplicateModel: (id) => set((state) => {
        const model = state.models.find(item => item.id === id);
        return model ? { models: [...state.models, { ...model, id: `model_${Date.now()}`, name: `${model.name} copy`, lastModified: 'Just now' }] } : state;
      }),
      setActiveModel: (id) => set({ activeModelId: id }),

      addWorkspace: (ws) => set((state) => ({ 
        workspaces: [...state.workspaces, ws],
        activeWorkspaceId: ws.id 
      })),
      removeWorkspace: (id) => set((state) => ({
        workspaces: state.workspaces.filter(w => w.id !== id),
        activeWorkspaceId: state.activeWorkspaceId === id ? (state.workspaces.find(w => w.id !== id)?.id || null) : state.activeWorkspaceId,
        studies: state.studies.filter(s => s.workspaceId !== id),
        datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => state.studies.find(study => study.id === studyId)?.workspaceId !== id)),
      })),
      archiveWorkspace: (id) => set((state) => {
        const workspace = state.workspaces.find(item => item.id === id);
        return workspace ? {
          workspaces: state.workspaces.filter(item => item.id !== id),
          archivedWorkspaces: [...state.archivedWorkspaces, { ...workspace, archivedAt: workspace.archivedAt || new Date().toISOString() }],
          activeWorkspaceId: state.activeWorkspaceId === id ? (state.workspaces.find(item => item.id !== id)?.id || null) : state.activeWorkspaceId
        } : state;
      }),
      restoreWorkspace: (id) => set((state) => {
        const workspace = state.archivedWorkspaces.find(item => item.id === id);
        return workspace ? {
          workspaces: [...state.workspaces, workspace],
          archivedWorkspaces: state.archivedWorkspaces.filter(item => item.id !== id)
        } : state;
      }),
      deleteWorkspace: (id) => set((state) => {
        const workspaceStudies = state.studies.filter(study => study.workspaceId === id);
        const studyIds = new Set(workspaceStudies.map(study => study.id));
        const remainingTabs = state.tabs.filter(tab => tab.workspaceId !== id);
        const nextTabs = remainingTabs.length > 0 ? remainingTabs : [{ id: 'get-started', type: 'get-started' as const, title: 'Home' }];
        const nextActiveTabId = nextTabs.some(t => t.id === state.activeTabId) ? state.activeTabId : nextTabs[0].id;
        return {
          workspaces: state.workspaces.filter(item => item.id !== id),
          archivedWorkspaces: state.archivedWorkspaces.filter(item => item.id !== id),
          studies: state.studies.filter(study => study.workspaceId !== id),
          models: state.models.filter(model => !studyIds.has(model.studyId)),
          datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => !studyIds.has(studyId))),
          activeWorkspaceId: state.activeWorkspaceId === id ? state.workspaces.find(item => item.id !== id)?.id ?? null : state.activeWorkspaceId,
          tabs: nextTabs,
          activeTabId: nextActiveTabId,
        };
      }),
      deleteStudy: (id) => set((state) => {
        const remainingTabs = state.tabs.filter(tab => tab.studyId !== id);
        const nextTabs = remainingTabs.length > 0 ? remainingTabs : [{ id: 'get-started', type: 'get-started' as const, title: 'Home' }];
        const nextActiveTabId = nextTabs.some(t => t.id === state.activeTabId) ? state.activeTabId : nextTabs[0].id;
        return {
          studies: state.studies.filter(item => item.id !== id),
          models: state.models.filter(model => model.studyId !== id),
          datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => studyId !== id)),
          activeStudyId: state.activeStudyId === id ? null : state.activeStudyId,
          tabs: nextTabs,
          activeTabId: nextActiveTabId,
        };
      }),
      deleteModel: (id) => set((state) => {
        const remainingTabs = state.tabs.filter(tab => tab.modelId !== id);
        const nextTabs = remainingTabs.length > 0 ? remainingTabs : [{ id: 'get-started', type: 'get-started' as const, title: 'Home' }];
        const nextActiveTabId = nextTabs.some(t => t.id === state.activeTabId) ? state.activeTabId : nextTabs[0].id;
        return {
          models: state.models.filter(item => item.id !== id),
          activeModelId: state.activeModelId === id ? null : state.activeModelId,
          tabs: nextTabs,
          activeTabId: nextActiveTabId,
        };
      }),
      deleteDataset: (studyId) => set((state) => ({
        datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([id]) => id !== studyId))
      })),
      renameWorkspace: (id, name) => set((state) => ({
        workspaces: state.workspaces.map(workspace => workspace.id === id ? { ...workspace, name } : workspace),
        tabs: state.tabs.map(tab => tab.type === 'workspace' && tab.workspaceId === id ? { ...tab, title: name } : tab),
      })),
      setActiveWorkspace: (id) => set({ activeWorkspaceId: id }),
      addStudy: (study) => set((state) => {
        const existingIdx = state.studies.findIndex(
          s => s.id === study.id || (s.workspaceId === study.workspaceId && (s.path === study.path || s.name.toLowerCase() === study.name.toLowerCase()))
        );
        if (existingIdx >= 0) {
          const updated = [...state.studies];
          updated[existingIdx] = { ...updated[existingIdx], ...study };
          return {
            studies: updated,
            activeStudyId: study.id
          };
        }
        return {
          studies: [...state.studies, study],
          activeStudyId: study.id
        };
      }),
      syncWorkspaceStudies: (workspaceId, diskProjects) => set((state) => {
        const otherStudies = state.studies.filter(s => s.workspaceId !== workspaceId);
        const currentStudies = state.studies.filter(s => s.workspaceId === workspaceId);

        const merged: Study[] = [];
        const seenKeys = new Set<string>();

        for (const dp of diskProjects) {
          const key = (dp.fullPath || dp.path || dp.name).toLowerCase();
          if (seenKeys.has(key)) continue;
          seenKeys.add(key);

          const existing = currentStudies.find(
            s => s.id === dp.fullPath || s.path === dp.fullPath || s.name.toLowerCase() === dp.name.toLowerCase()
          );

          if (existing) {
            merged.push({
              ...existing,
              id: existing.id || dp.fullPath,
              name: dp.name,
              path: dp.fullPath
            });
          } else {
            merged.push({
              id: dp.fullPath,
              workspaceId,
              name: dp.name,
              type: 'PLS-SEM',
              description: '',
              lastModified: 'Saved',
              path: dp.fullPath
            });
          }
        }

        return {
          studies: [...otherStudies, ...merged]
        };
      }),
      removeStudy: (id) => set((state) => ({
        studies: state.studies.filter(s => s.id !== id),
        activeStudyId: state.activeStudyId === id ? null : state.activeStudyId,
        models: state.models.filter(m => m.studyId !== id),
        datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => studyId !== id)),
      })),
      renameStudy: (id, name) => set((state) => ({ studies: state.studies.map(study => study.id === id ? { ...study, name, lastModified: 'Just now' } : study) })),
      duplicateStudy: (id) => set((state) => {
        const study = state.studies.find(item => item.id === id);
        if (!study) return state;
        const studyId = `study_${Date.now()}`;
        const dataset = state.datasetsByStudy[id];
        return {
          studies: [...state.studies, { ...study, id: studyId, name: `${study.name} copy`, lastModified: 'Just now' }],
          models: [...state.models, ...state.models.filter(model => model.studyId === id).map(model => ({ ...model, id: `model_${Date.now()}_${model.id}`, studyId, name: `${model.name} copy`, lastModified: 'Just now' }))],
          datasetsByStudy: dataset ? { ...state.datasetsByStudy, [studyId]: { ...dataset, variables: dataset.variables.map(variable => ({ ...variable })), rows: dataset.rows.map(row => [...row]) } } : state.datasetsByStudy,
        };
      }),
      setActiveStudy: (id) => set({ activeStudyId: id }),
      setStudyDataset: (studyId, dataset) => set((state) => ({
        datasetsByStudy: { ...state.datasetsByStudy, [studyId]: dataset }
      })),
      removeStudyDataset: (studyId) => set((state) => ({
        datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([id]) => id !== studyId))
      })),
      touchStudy: (id) => set((state) => ({ studies: state.studies.map(study => study.id === id ? { ...study, lastModified: 'Just now' } : study) })),
      
      // Variables
      variables: INITIAL_VARIABLES,
      
      // Canvas State
      nodes: [],
      edges: [],
      selectedIds: new Set(),
      mode: 'select',
      zoom: 1,
      pan: { x: 0, y: 0 },
      
      addNode: (node) => set((state) => ({ nodes: [...state.nodes, node] })),
      
      updateNode: (id, data) => set((state) => ({
        nodes: state.nodes.map(n => n.id === id ? { ...n, ...data } : n)
      })),
      
      removeNodes: (ids) => set((state) => ({
        nodes: state.nodes.filter(n => !ids.includes(n.id)),
        edges: state.edges.filter(e => !ids.includes(e.sourceId) && !ids.includes(e.targetId)),
        selectedIds: new Set([...state.selectedIds].filter(id => !ids.includes(id)))
      })),
      
      addEdge: (sourceId, targetId) => set((state) => {
        if (state.edges.some(e => e.sourceId === targetId && e.targetId === sourceId)) return state;
        if (state.edges.some(e => e.sourceId === sourceId && e.targetId === targetId)) return state;
        return { edges: [...state.edges, { id: `${sourceId}-${targetId}`, sourceId, targetId }] };
      }),
      
      removeEdges: (ids) => set((state) => ({
        edges: state.edges.filter(e => !ids.includes(e.id)),
        selectedIds: new Set([...state.selectedIds].filter(id => !ids.includes(id)))
      })),
      
      setMode: (mode) => set({ mode, selectedIds: new Set() }),
      setSelection: (ids) => set({ selectedIds: new Set(ids) }),
      clearSelection: () => set({ selectedIds: new Set() }),
      setZoom: (zoom) => set({ zoom }),
      setPan: (x, y) => set({ pan: { x, y } }),

      contextMenu: null,
      openContextMenu: (x, y, items) => set({ contextMenu: { x, y, items } }),
      closeContextMenu: () => set({ contextMenu: null }),
    }),
    {
      name: 'cspls-storage', // name of the item in the storage (must be unique)
      partialize: (state) => ({
        workspaces: state.workspaces,
        archivedWorkspaces: state.archivedWorkspaces,
        studies: state.studies,
        models: state.models,
        datasetsByStudy: state.datasetsByStudy,
        activeWorkspaceId: state.activeWorkspaceId,
        theme: state.theme,
        settings: state.settings,
        isSidebarCollapsed: state.isSidebarCollapsed,
      }), // only persist these fields
      merge: (persistedState: any, currentState: AppState) => ({
        ...currentState,
        ...persistedState,
        settings: {
          ...INITIAL_SETTINGS,
          ...(persistedState?.settings || {}),
        },
      }),
    }
  )
);
