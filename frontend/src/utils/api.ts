const API_BASE = 'http://127.0.0.1:8721';

export interface WorkspaceMetadata {
  name: string;
  created_at: string;
  modified_at: string;
  projects: Array<{ path: string; name: string }>;
}

export interface WorkspaceResponse {
  status?: string;
  path?: string;
  workspace?: WorkspaceMetadata;
  error?: string;
}

export interface RecentWorkspace {
  path: string;
  name: string;
  modified_at: string;
  workspace_count: number;
}

export interface ProjectResponse {
  status?: string;
  project_path?: string;
  workspace?: WorkspaceMetadata;
  error?: string;
}

export const api = {
  async createWorkspace(folderPath: string, name: string): Promise<WorkspaceResponse> {
    try {
      const res = await fetch(
        `${API_BASE}/workspace/create?folder_path=${encodeURIComponent(folderPath)}&name=${encodeURIComponent(name)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to connect to backend server' };
    }
  },

  async openWorkspace(folderPath: string): Promise<WorkspaceResponse> {
    try {
      const res = await fetch(
        `${API_BASE}/workspace/open?folder_path=${encodeURIComponent(folderPath)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to connect to backend server' };
    }
  },

  async getRecentWorkspaces(): Promise<RecentWorkspace[]> {
    try {
      const res = await fetch(`${API_BASE}/workspace/recent`);
      return await res.json();
    } catch {
      return [];
    }
  },

  async deleteWorkspace(folderPath: string): Promise<{ status?: string; error?: string }> {
    try {
      const res = await fetch(
        `${API_BASE}/workspace/delete?folder_path=${encodeURIComponent(folderPath)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to delete workspace' };
    }
  },

  async addProject(folderPath: string, projectName: string): Promise<ProjectResponse> {
    try {
      const res = await fetch(
        `${API_BASE}/workspace/add-project?folder_path=${encodeURIComponent(folderPath)}&project_name=${encodeURIComponent(projectName)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to connect to backend server' };
    }
  },

  async removeProject(folderPath: string, projectFilename: string): Promise<{ status?: string; workspace?: WorkspaceMetadata; error?: string }> {
    try {
      const res = await fetch(
        `${API_BASE}/workspace/remove-project?folder_path=${encodeURIComponent(folderPath)}&project_filename=${encodeURIComponent(projectFilename)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to remove project from workspace' };
    }
  },

  async deleteProject(folderPath: string, projectFilename: string): Promise<{ status?: string; workspace?: WorkspaceMetadata; error?: string }> {
    try {
      const res = await fetch(
        `${API_BASE}/workspace/delete-project?folder_path=${encodeURIComponent(folderPath)}&project_filename=${encodeURIComponent(projectFilename)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to delete project' };
    }
  },

  async openProject(path: string): Promise<{ status?: string; path?: string; error?: string }> {
    try {
      const res = await fetch(
        `${API_BASE}/project/open?path=${encodeURIComponent(path)}`,
        { method: 'POST' }
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to open project' };
    }
  },

  async getRecentProjects(): Promise<Array<{ path: string; name: string; modified_at: string }>> {
    try {
      const res = await fetch(`${API_BASE}/project/recent`);
      return await res.json();
    } catch {
      return [];
    }
  },

  async saveProjectData(path: string, file: File): Promise<{ status?: string; row_count?: number; dataset_name?: string; error?: string }> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/project/save-data?path=${encodeURIComponent(path)}`, {
        method: 'POST',
        body: formData,
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to save project data' };
    }
  },

  async saveProjectDataJson(
    path: string,
    datasetName: string,
    columns: string[],
    rows: any[][]
  ): Promise<{ status?: string; row_count?: number; dataset_name?: string; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/save-data-json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          dataset_name: datasetName,
          columns,
          rows
        })
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to save project data' };
    }
  },

  async loadProjectData(path: string): Promise<{ columns?: string[]; rows?: any[][]; dataset_name?: string; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/load-data?path=${encodeURIComponent(path)}`);
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to load project data' };
    }
  },

  async deleteProjectData(path: string): Promise<{ status?: string; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/delete-data?path=${encodeURIComponent(path)}`, {
        method: 'POST'
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to delete project data' };
    }
  },
};
