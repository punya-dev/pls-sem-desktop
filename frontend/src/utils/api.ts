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

export interface ConstructSpec {
  id: string;
  name: string;
  type: 'reflective' | 'formative';
  indicators: string[];
}

export interface IndicatorSpec {
  id: string;
  column: string;
}

export interface PathSpec {
  from: string;
  to: string;
}

export interface ModelSpec {
  constructs: ConstructSpec[];
  indicators: IndicatorSpec[];
  paths: PathSpec[];
}

export interface ValidationResponse {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  exogenous_constructs: string[];
  endogenous_constructs: string[];
  isolated_constructs: string[];
  error?: string;
}

export interface SaveModelResponse {
  status?: string;
  validation?: ValidationResponse;
  error?: string;
}

export interface LoadModelResponse {
  spec?: ModelSpec | null;
  diagram_layout?: any | null;
  updated_at?: string | null;
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

  async saveProjectData(
    path: string,
    file: File,
    missingValue?: string,
    treatment?: string
  ): Promise<{ status?: string; row_count?: number; dataset_name?: string; error?: string }> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      let url = `${API_BASE}/project/save-data?path=${encodeURIComponent(path)}`;
      if (missingValue) url += `&missing_value=${encodeURIComponent(missingValue)}`;
      if (treatment && treatment !== 'none') url += `&treatment=${encodeURIComponent(treatment)}`;

      const res = await fetch(url, {
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
    rows: any[][],
    missingValue?: string,
    treatment?: string
  ): Promise<{ status?: string; row_count?: number; dataset_name?: string; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/save-data-json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          dataset_name: datasetName,
          columns,
          rows,
          missing_value: missingValue,
          treatment: treatment && treatment !== 'none' ? treatment : undefined
        })
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to save project data' };
    }
  },

  async treatMissing(
    path: string,
    method: 'listwise' | 'mean',
    missingValue?: string
  ): Promise<{ status?: string; method?: string; original_row_count?: number; cleaned_row_count?: number; rows_dropped?: number; error?: string }> {
    try {
      let url = `${API_BASE}/project/treat-missing?path=${encodeURIComponent(path)}&method=${method}`;
      if (missingValue) url += `&missing_value=${encodeURIComponent(missingValue)}`;
      const res = await fetch(url, { method: 'POST' });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to treat missing values' };
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

  async validateModel(
    spec: ModelSpec,
    projectPath?: string,
    datasetColumns?: string[]
  ): Promise<ValidationResponse> {
    try {
      const res = await fetch(`${API_BASE}/model/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spec,
          project_path: projectPath,
          dataset_columns: datasetColumns,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return {
        is_valid: false,
        errors: [err?.message || 'Failed to connect to backend server'],
        warnings: [],
        exogenous_constructs: [],
        endogenous_constructs: [],
        isolated_constructs: [],
        error: err?.message,
      };
    }
  },

  async saveProjectModel(
    projectPath: string,
    spec: ModelSpec,
    diagramLayout?: any
  ): Promise<SaveModelResponse> {
    try {
      const res = await fetch(`${API_BASE}/project/save-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          spec,
          diagram_layout: diagramLayout,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to save model' };
    }
  },

  async loadProjectModel(projectPath: string): Promise<LoadModelResponse> {
    try {
      const res = await fetch(
        `${API_BASE}/project/load-model?path=${encodeURIComponent(projectPath)}`
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to load model' };
    }
  },

  async runPlsModel(
    projectPath: string,
    spec?: ModelSpec,
    options?: {
      scheme?: string;
      max_iter?: number;
      tol?: number;
      bootstrap?: boolean;
      n_boot?: number;
      columns?: string[];
      rows?: any[][];
      dataset_name?: string;
    }
  ): Promise<{ status?: string; algorithm?: string; results?: any; validation?: ValidationResponse; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/run-pls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          spec: spec || undefined,
          scheme: options?.scheme || 'path',
          max_iter: options?.max_iter || 300,
          tol: options?.tol || 1e-7,
          bootstrap: options?.bootstrap || false,
          n_boot: options?.n_boot || 500,
          columns: options?.columns || undefined,
          rows: options?.rows || undefined,
          dataset_name: options?.dataset_name || undefined,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to execute PLS-SEM calculation' };
    }
  },

  async loadProjectResults(projectPath: string, algorithm: string = 'pls'): Promise<{ algorithm?: string; results?: any; created_at?: string; error?: string }> {
    try {
      const res = await fetch(
        `${API_BASE}/project/load-results?path=${encodeURIComponent(projectPath)}&algorithm=${encodeURIComponent(algorithm)}`
      );
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to load calculation results' };
    }
  },
};

