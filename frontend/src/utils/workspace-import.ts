import { api } from './api';
import { useStore } from '../store';
import { processData } from './dataset-parser';

type CreateWorkspaceWithProjectListener = (projectPath: string, projectName?: string) => void;
let createWsWithProjectListener: CreateWorkspaceWithProjectListener | null = null;

export function registerCreateWorkspaceWithProject(listener: CreateWorkspaceWithProjectListener) {
  createWsWithProjectListener = listener;
  return () => {
    if (createWsWithProjectListener === listener) {
      createWsWithProjectListener = null;
    }
  };
}

/**
 * Directly opens the native directory selector to import or open a workspace.
 * - CSPLS Workspace: Opened immediately.
 * - SmartPLS Workspace: Imported and opened immediately.
 * - SmartPLS Project folder: Prompts the Create New Workspace modal with that project.
 */
export async function promptOpenWorkspaceFolder(): Promise<void> {
  let selectedPath: string | null = null;
  try {
    const { open } = await import('@tauri-apps/plugin-dialog');
    const selected = await open({
      directory: true,
      multiple: false,
      title: 'Import / Open Workspace'
    });
    if (selected && typeof selected === 'string') {
      selectedPath = selected;
    }
  } catch (err) {
    console.warn('Tauri dialog not available, falling back to prompt:', err);
    const fallback = window.prompt('Enter folder path to import / open workspace:');
    if (fallback) {
      selectedPath = fallback;
    }
  }

  if (!selectedPath) return;

  try {
    const detection = await api.detectFolder(selectedPath);

    if (detection.kind === 'cspls_workspace') {
      // 1. Existing CSPLS Workspace
      const res = await api.openWorkspace(selectedPath);
      if (res?.error) {
        alert(`Failed to open workspace: ${res.error}`);
        return;
      }
      const wsName = detection.name || selectedPath.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() || 'Workspace';
      const state = useStore.getState();
      const existing = state.workspaces.find(w => w.path === selectedPath);
      if (!existing) {
        state.addWorkspace({
          id: selectedPath,
          name: wsName,
          path: selectedPath,
        });
      }
      state.setActiveWorkspace(selectedPath);
      state.openTab({
        type: 'workspace',
        title: wsName,
        workspaceId: selectedPath,
      });
      return;
    }

    if (detection.kind === 'smartpls_workspace') {
      // 2. SmartPLS Workspace (e.g. Work folder containing SmartPLS projects)
      const res = await api.importSmartPlsWorkspace(selectedPath);
      if (res?.error) {
        alert(`Failed to import SmartPLS workspace: ${res.error}`);
        return;
      }
      const wsName = res.workspace?.name || detection.name || 'Workspace';
      const state = useStore.getState();
      const existing = state.workspaces.find(w => w.path === selectedPath);
      if (!existing) {
        state.addWorkspace({
          id: selectedPath,
          name: wsName,
          path: selectedPath,
        });
      }
      if (res.studies && res.studies.length > 0) {
        for (const s of res.studies) {
          state.addStudy({
            id: s.id,
            workspaceId: selectedPath,
            name: s.name,
            type: s.type || 'PLS-SEM',
            description: s.description || '',
            lastModified: 'Just now',
            path: s.path,
            createdAt: s.createdAt,
          });
          try {
            const dRes = await api.loadProjectData(s.path);
            if (dRes?.rows && dRes?.columns) {
              const parsed = processData(dRes.dataset_name || s.name, dRes.columns, dRes.rows);
              state.setStudyDataset(s.id, parsed);
            }
          } catch (e) {
            console.warn('Could not load data for study', s.name, e);
          }
        }
        state.setActiveStudy(res.studies[0].id);
      }
      if (res.models && res.models.length > 0) {
        for (const m of res.models) {
          state.addModel({
            id: m.id,
            studyId: m.studyId,
            name: m.name,
            type: m.type || 'pls',
            lastModified: 'Just now',
          });
        }
      }
      state.setActiveWorkspace(selectedPath);
      state.openTab({
        type: 'workspace',
        title: wsName,
        workspaceId: selectedPath,
      });
      return;
    }

    if (detection.kind === 'smartpls_project') {
      // 3. User selected a project folder instead of a workspace folder
      // Prompt the create new workspace modal and add that project there
      if (createWsWithProjectListener) {
        createWsWithProjectListener(selectedPath, detection.project_name);
      } else {
        alert(`Selected folder "${detection.project_name || selectedPath}" is a SmartPLS project. Please create or open a workspace first.`);
      }
      return;
    }

    // 4. Default / unknown directory -> prompt Create Workspace dialog with this path
    if (createWsWithProjectListener) {
      createWsWithProjectListener('', selectedPath.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop());
    } else {
      alert(`The selected folder is not a recognised workspace.`);
    }
  } catch (err: any) {
    console.error('Error opening/importing workspace:', err);
    alert(`Could not open or import workspace: ${err?.message || err}`);
  }
}
