import { api } from './api';
import { useStore } from '../store';

/**
 * Prompts the user to pick a folder from their computer using the native
 * file manager dialog and opens/imports it as a workspace.
 */
export async function promptOpenWorkspaceFolder(): Promise<{ success: boolean; error?: string }> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog');
    const selected = await open({
      directory: true,
      multiple: false,
      title: 'Open / Import Workspace Folder',
    });

    if (selected && typeof selected === 'string') {
      const state = useStore.getState();
      const res = await api.openWorkspace(selected);
      if (res?.error) {
        alert(res.error);
        return { success: false, error: res.error };
      }

      const wsName =
        res?.workspace?.name ||
        selected.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() ||
        'Workspace';

      const existing = state.workspaces.find((w) => w.path === selected);
      const wsId = existing ? existing.id : selected;

      if (!existing) {
        state.addWorkspace({
          id: wsId,
          name: wsName,
          path: selected,
          createdAt: new Date().toISOString(),
          modifiedAt: new Date().toISOString(),
        });
      }

      state.setActiveWorkspace(wsId);
      state.openTab({ type: 'workspace', title: wsName, workspaceId: wsId });
      return { success: true };
    }
    return { success: false };
  } catch (err: any) {
    console.warn('Tauri open dialog error, using fallback prompt:', err);
    const fallback = window.prompt('Enter workspace directory path:');
    if (fallback) {
      const state = useStore.getState();
      const res = await api.openWorkspace(fallback);
      if (res?.error) {
        alert(res.error);
        return { success: false, error: res.error };
      }

      const wsName =
        res?.workspace?.name ||
        fallback.replace(/[/\\]+$/, '').split(/[/\\]/).filter(Boolean).pop() ||
        'Workspace';

      const existing = state.workspaces.find((w) => w.path === fallback);
      const wsId = existing ? existing.id : fallback;

      if (!existing) {
        state.addWorkspace({
          id: wsId,
          name: wsName,
          path: fallback,
          createdAt: new Date().toISOString(),
          modifiedAt: new Date().toISOString(),
        });
      }

      state.setActiveWorkspace(wsId);
      state.openTab({ type: 'workspace', title: wsName, workspaceId: wsId });
      return { success: true };
    }
    return { success: false };
  }
}
