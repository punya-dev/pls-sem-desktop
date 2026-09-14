import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ParsedDataset } from './utils/dataset-parser';

export type ShapeType = 'circle' | 'rect' | 'hexagon' | 'octagon';

export interface Workspace {
  id: string;
  name: string;
  path: string;
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

export type TrashItem =
  | { id: string; kind: 'workspace'; name: string; deletedAt: string; workspace: Workspace; studies: Study[]; models: Model[]; datasets: Record<string, ParsedDataset> }
  | { id: string; kind: 'study'; name: string; deletedAt: string; workspaceName?: string; study: Study; models: Model[]; dataset?: ParsedDataset }
  | { id: string; kind: 'model'; name: string; deletedAt: string; workspaceName?: string; studyName?: string; model: Model }
  | { id: string; kind: 'dataset'; name: string; deletedAt: string; workspaceName?: string; studyName?: string; studyId: string; dataset: ParsedDataset };

interface AppState {
  // Global
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  
  // Workspaces & Studies
  workspaces: Workspace[];
  archivedWorkspaces: Workspace[];
  trash: TrashItem[];
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
  trashWorkspace: (id: string) => void;
  trashStudy: (id: string) => void;
  trashModel: (id: string) => void;
  trashDataset: (studyId: string) => void;
  restoreTrashItem: (id: string) => void;
  permanentlyDeleteTrashItem: (id: string) => void;
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

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      // Global
      theme: 'light',
      toggleTheme: () => set((state) => ({ theme: state.theme === 'light' ? 'dark' : 'light' })),
      
      // Workspaces & Studies
      workspaces: INITIAL_WORKSPACES,
      archivedWorkspaces: [],
      trash: [],
      activeWorkspaceId: null,
      studies: INITIAL_STUDIES,
      activeStudyId: null,
      models: INITIAL_MODELS,
      datasetsByStudy: {},
      activeModelId: null,
      addModel: (model) => set((state) => ({ models: [...state.models, model] })),
      removeModel: (id) => set((state) => ({ models: state.models.filter(model => model.id !== id) })),
      renameModel: (id, name) => set((state) => ({ models: state.models.map(model => model.id === id ? { ...model, name, lastModified: 'Just now' } : model) })),
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
        return workspace ? { workspaces: state.workspaces.filter(item => item.id !== id), archivedWorkspaces: [...state.archivedWorkspaces, workspace], activeWorkspaceId: state.activeWorkspaceId === id ? (state.workspaces.find(item => item.id !== id)?.id || null) : state.activeWorkspaceId } : state;
      }),
      restoreWorkspace: (id) => set((state) => {
        const workspace = state.archivedWorkspaces.find(item => item.id === id);
        return workspace ? { workspaces: [...state.workspaces, workspace], archivedWorkspaces: state.archivedWorkspaces.filter(item => item.id !== id) } : state;
      }),
      trashWorkspace: (id) => set((state) => {
        const workspace = state.workspaces.find(item => item.id === id);
        if (!workspace) return state;
        const workspaceStudies = state.studies.filter(study => study.workspaceId === id);
        const studyIds = new Set(workspaceStudies.map(study => study.id));
        const datasets = Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => studyIds.has(studyId)));
        const item: TrashItem = { id: `trash_${Date.now()}`, kind: 'workspace', name: workspace.name, deletedAt: new Date().toLocaleString(), workspace, studies: workspaceStudies, models: state.models.filter(model => studyIds.has(model.studyId)), datasets };
        return { trash: [item, ...state.trash], workspaces: state.workspaces.filter(item => item.id !== id), studies: state.studies.filter(study => study.workspaceId !== id), models: state.models.filter(model => !studyIds.has(model.studyId)), datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => !studyIds.has(studyId))), activeWorkspaceId: state.activeWorkspaceId === id ? state.workspaces.find(item => item.id !== id)?.id ?? null : state.activeWorkspaceId };
      }),
      trashStudy: (id) => set((state) => {
        const study = state.studies.find(item => item.id === id);
        if (!study) return state;
        const workspaceName = state.workspaces.find(workspace => workspace.id === study.workspaceId)?.name;
        const item: TrashItem = { id: `trash_${Date.now()}`, kind: 'study', name: study.name, deletedAt: new Date().toLocaleString(), workspaceName, study, models: state.models.filter(model => model.studyId === id), dataset: state.datasetsByStudy[id] };
        return { trash: [item, ...state.trash], studies: state.studies.filter(item => item.id !== id), models: state.models.filter(model => model.studyId !== id), datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([studyId]) => studyId !== id)), activeStudyId: state.activeStudyId === id ? null : state.activeStudyId };
      }),
      trashModel: (id) => set((state) => {
        const model = state.models.find(item => item.id === id);
        const study = model ? state.studies.find(item => item.id === model.studyId) : undefined;
        const workspaceName = study ? state.workspaces.find(workspace => workspace.id === study.workspaceId)?.name : undefined;
        return model ? { trash: [{ id: `trash_${Date.now()}`, kind: 'model', name: model.name, deletedAt: new Date().toLocaleString(), workspaceName, studyName: study?.name, model }, ...state.trash], models: state.models.filter(item => item.id !== id), activeModelId: state.activeModelId === id ? null : state.activeModelId } : state;
      }),
      trashDataset: (studyId) => set((state) => {
        const dataset = state.datasetsByStudy[studyId];
        const study = state.studies.find(item => item.id === studyId);
        const workspaceName = study ? state.workspaces.find(workspace => workspace.id === study.workspaceId)?.name : undefined;
        return dataset ? { trash: [{ id: `trash_${Date.now()}`, kind: 'dataset', name: dataset.filename, deletedAt: new Date().toLocaleString(), workspaceName, studyName: study?.name, studyId, dataset }, ...state.trash], datasetsByStudy: Object.fromEntries(Object.entries(state.datasetsByStudy).filter(([id]) => id !== studyId)) } : state;
      }),
      restoreTrashItem: (id) => set((state) => {
        const item = state.trash.find(entry => entry.id === id);
        if (!item) return state;
        const base = { trash: state.trash.filter(entry => entry.id !== id) };
        if (item.kind === 'workspace') return { ...base, workspaces: [...state.workspaces, item.workspace], studies: [...state.studies, ...item.studies], models: [...state.models, ...item.models], datasetsByStudy: { ...state.datasetsByStudy, ...item.datasets } };
        if (item.kind === 'study') return { ...base, studies: [...state.studies, item.study], models: [...state.models, ...item.models], datasetsByStudy: item.dataset ? { ...state.datasetsByStudy, [item.study.id]: item.dataset } : state.datasetsByStudy };
        if (item.kind === 'model') return { ...base, models: [...state.models, item.model] };
        return { ...base, datasetsByStudy: { ...state.datasetsByStudy, [item.studyId]: item.dataset } };
      }),
      permanentlyDeleteTrashItem: (id) => set((state) => ({ trash: state.trash.filter(item => item.id !== id) })),
      renameWorkspace: (id, name) => set((state) => ({ workspaces: state.workspaces.map(workspace => workspace.id === id ? { ...workspace, name } : workspace) })),
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
        trash: state.trash,
        studies: state.studies,
        models: state.models,
        datasetsByStudy: state.datasetsByStudy,
        activeWorkspaceId: state.activeWorkspaceId,
        theme: state.theme,
      }), // only persist these fields
    }
  )
);
