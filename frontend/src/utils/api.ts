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
    diagramLayout?: any,
    modelId?: string
  ): Promise<SaveModelResponse> {
    try {
      const res = await fetch(`${API_BASE}/project/save-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          spec,
          diagram_layout: diagramLayout,
          model_id: modelId,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to save model' };
    }
  },

  async loadProjectModel(projectPath: string, modelId?: string): Promise<LoadModelResponse> {
    try {
      const url = modelId
        ? `${API_BASE}/project/load-model?path=${encodeURIComponent(projectPath)}&model_id=${encodeURIComponent(modelId)}`
        : `${API_BASE}/project/load-model?path=${encodeURIComponent(projectPath)}`;
      const res = await fetch(url);
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to load model' };
    }
  },

  async duplicateModel(projectPath: string, sourceModelId: string, newModelId: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/duplicate-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          source_model_id: sourceModelId,
          new_model_id: newModelId,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to duplicate model' };
    }
  },

  async duplicateProject(folderPath: string, sourcePath: string, newName: string, modelIdMap?: Record<string, string>): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder_path: folderPath,
          source_path: sourcePath,
          new_name: newName,
          model_id_map: modelIdMap,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to duplicate project' };
    }
  },

  async remapModelIds(projectPath: string, modelIdMap: Record<string, string>): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/remap-model-ids`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          model_id_map: modelIdMap,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to remap model ids' };
    }
  },

  async duplicateWorkspace(sourceFolderPath: string, newName: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/workspace/duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_folder_path: sourceFolderPath,
          new_name: newName,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to duplicate workspace' };
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
      model_id?: string;
      diagram_layout?: any;
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
          model_id: options?.model_id || undefined,
          diagram_layout: options?.diagram_layout || undefined,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to execute PLS-SEM calculation' };
    }
  },

  async loadProjectResults(
    projectPath: string,
    algorithm: string = 'pls',
    modelId?: string
  ): Promise<{ algorithm?: string; results?: any; created_at?: string; spec?: any; diagram_layout?: any; error?: string }> {
    try {
      let url = `${API_BASE}/project/load-results?path=${encodeURIComponent(projectPath)}&algorithm=${encodeURIComponent(algorithm)}`;
      if (modelId) {
        url += `&model_id=${encodeURIComponent(modelId)}`;
      }
      const res = await fetch(url);
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to load calculation results' };
    }
  },

  async startBootstrap(
    projectPath: string,
    spec?: ModelSpec,
    options?: {
      n_boot?: number;
      seed?: number;
      scheme?: string;
      columns?: string[];
      rows?: any[][];
      dataset_name?: string;
      model_id?: string;
      diagram_layout?: any;
    }
  ): Promise<{ status?: string; job_id?: string; n_boot?: number; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/bootstrap-start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          spec: spec || undefined,
          n_boot: options?.n_boot || 500,
          seed: options?.seed !== undefined ? options.seed : 42,
          scheme: options?.scheme || 'path',
          columns: options?.columns || undefined,
          rows: options?.rows || undefined,
          dataset_name: options?.dataset_name || undefined,
          model_id: options?.model_id || undefined,
          diagram_layout: options?.diagram_layout || undefined,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to start bootstrapping' };
    }
  },

  async cancelBootstrap(jobId: string): Promise<{ status?: string; job_id?: string; error?: string }> {
    try {
      const res = await fetch(`${API_BASE}/project/bootstrap-cancel?job_id=${encodeURIComponent(jobId)}`, {
        method: 'POST',
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to cancel bootstrapping' };
    }
  },

  async getBootstrapStatus(jobId: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/bootstrap-status?job_id=${encodeURIComponent(jobId)}`);
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to get bootstrap status' };
    }
  },

  createBootstrapWebSocket(
    jobId: string,
    onMessage: (data: any) => void,
    onError?: (err: any) => void,
    onClose?: () => void
  ): WebSocket {
    const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws/bootstrap-progress/${encodeURIComponent(jobId)}`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('Failed to parse WS message', e);
      }
    };
    if (onError) ws.onerror = onError;
    if (onClose) ws.onclose = onClose;
    return ws;
  },

  async saveSnapshot(data: {
    projectPath: string;
    name: string;
    description?: string;
    algorithm?: string;
    results: any;
    spec: any;
    diagramLayout: any;
    sourceModelId?: string;
  }): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/save-snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: data.projectPath,
          name: data.name,
          description: data.description || '',
          algorithm: data.algorithm || 'pls',
          results: data.results,
          spec: data.spec,
          diagram_layout: data.diagramLayout,
          source_model_id: data.sourceModelId,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to save snapshot' };
    }
  },

  async listSnapshots(projectPath: string): Promise<any[]> {
    try {
      const res = await fetch(`${API_BASE}/project/list-snapshots?path=${encodeURIComponent(projectPath)}`);
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    } catch (err: any) {
      console.warn('Failed to list snapshots:', err);
      return [];
    }
  },

  async getSnapshot(projectPath: string, snapshotId: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/get-snapshot?path=${encodeURIComponent(projectPath)}&snapshot_id=${encodeURIComponent(snapshotId)}`);
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to get snapshot' };
    }
  },

  async deleteSnapshot(projectPath: string, snapshotId: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/delete-snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          snapshot_id: snapshotId,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to delete snapshot' };
    }
  },

  async createModelFromSnapshot(projectPath: string, snapshotId: string, newModelId: string, newModelName: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/project/create-model-from-snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          snapshot_id: snapshotId,
          new_model_id: newModelId,
          new_model_name: newModelName,
        }),
      });
      return await res.json();
    } catch (err: any) {
      return { error: err?.message || 'Failed to create model from snapshot' };
    }
  },
};


