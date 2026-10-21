import { api } from './api';
import { useStore } from '../store';
import { processData } from './dataset-parser';

/**
 * Prompts user to select a SmartPLS export directory, decrypts models & reports,
 * parses datasets, and imports them as a fully populated Workspace & Studies.
 */
export async function promptImportSmartPlsFolder(
  targetWorkspacePath?: string,
  targetWorkspaceName?: string
): Promise<{ success: boolean; error?: string }> {
  try {
    let selected: string | null = null;
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const dialogRes = await open({
        directory: true,
        multiple: false,
        title: 'Select SmartPLS Export Folder',
      });
      if (dialogRes && typeof dialogRes === 'string') {
        selected = dialogRes;
      }
    } catch (e) {
      console.warn('Tauri dialog error, falling back to prompt:', e);
      selected = window.prompt('Enter path to SmartPLS export directory:');
    }

    if (!selected) return { success: false };

    // 1. Detect SmartPLS project
    const detectRes = await api.detectSmartPls(selected);
    if (!detectRes || !detectRes.valid) {
      const msg = detectRes?.error || 'The selected folder does not appear to contain SmartPLS export files (.splsm).';
      alert(msg);
      return { success: false, error: msg };
    }

    // 2. Perform Import via backend
    const importRes = await api.importSmartPls(selected, targetWorkspacePath, targetWorkspaceName);
    if (importRes.error || !importRes.workspace) {
      const msg = importRes.error || 'Failed to import SmartPLS project.';
      alert(msg);
      return { success: false, error: msg };
    }

    const state = useStore.getState();

    // 3. Add or update Workspace in Zustand store
    const ws = importRes.workspace;
    const existingWs = state.workspaces.find((w) => w.path === ws.path || w.id === ws.id);
    if (!existingWs) {
      state.addWorkspace({
        id: ws.id,
        name: ws.name,
        path: ws.path,
        createdAt: ws.createdAt || new Date().toISOString(),
        modifiedAt: ws.modifiedAt || new Date().toISOString(),
      });
    }
    state.setActiveWorkspace(ws.id);

    // 4. Add Studies and load datasets
    if (importRes.studies && importRes.studies.length > 0) {
      for (const study of importRes.studies) {
        state.addStudy({
          id: study.id,
          workspaceId: ws.id,
          name: study.name,
          type: study.type || 'PLS-SEM',
          description: study.description || 'Imported from SmartPLS',
          lastModified: 'Just now',
          path: study.path,
          createdAt: study.createdAt || new Date().toISOString(),
        });

        // Load dataset from SQLite study file into store
        try {
          const dataRes = await api.loadProjectData(study.path);
          if (dataRes && Array.isArray(dataRes.columns) && Array.isArray(dataRes.rows)) {
            const parsed = processData(dataRes.dataset_name || study.name, dataRes.columns, dataRes.rows);
            state.setStudyDataset(study.id, parsed);
          }
        } catch (dataErr) {
          console.warn('Could not load data for imported study:', study.name, dataErr);
        }
      }
    }

    // 5. Add Models
    if (importRes.models && importRes.models.length > 0) {
      for (const model of importRes.models) {
        state.addModel({
          id: model.id,
          studyId: model.studyId,
          name: model.name,
          type: model.type || 'pls',
          lastModified: 'Just now',
        });
      }
    }

    // 6. Open the Workspace tab and the first Model tab
    state.openTab({
      type: 'workspace',
      title: ws.name,
      workspaceId: ws.id,
    });

    if (importRes.models && importRes.models.length > 0) {
      const firstModel = importRes.models[0];
      state.setActiveStudy(firstModel.studyId);
      state.setActiveModel(firstModel.id);
      state.openTab({
        type: 'model',
        title: firstModel.name,
        workspaceId: ws.id,
        studyId: firstModel.studyId,
        modelId: firstModel.id,
      });
    }

    alert(`Successfully imported SmartPLS project "${ws.name}" with ${importRes.models?.length || 0} models and ${importRes.studies?.length || 0} datasets!`);
    return { success: true };
  } catch (err: any) {
    const errorMsg = err?.message || 'An unexpected error occurred during SmartPLS import';
    alert(errorMsg);
    return { success: false, error: errorMsg };
  }
}
