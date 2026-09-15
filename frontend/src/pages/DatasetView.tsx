import React, { useState, useRef, useMemo, useEffect } from 'react';
import { useStore } from '../store';
import { processData, type ParsedDataset, type ParsedVariable } from '../utils/dataset-parser';
import { EditableCell } from '../components/EditableCell';
import { api } from '../utils/api';

export const DatasetView: React.FC = () => {
  const { 
    tabs, 
    activeTabId, 
    workspaces, 
    activeWorkspaceId, 
    studies, 
    activeStudyId, 
    datasetsByStudy, 
    setStudyDataset, 
    touchStudy, 
    openTab 
  } = useStore();

  const activeTab = tabs.find(t => t.id === activeTabId);
  const currentStudyId = activeTab?.studyId || activeStudyId || '';
  const activeWorkspace = workspaces.find(w => w.id === (activeTab?.workspaceId || activeWorkspaceId));
  const activeStudy = studies.find(s => s.id === currentStudyId);

  const initialDataset = currentStudyId ? datasetsByStudy[currentStudyId] : null;
  const [dataset, setDataset] = useState<ParsedDataset | null>(initialDataset);
  const [currentView, setCurrentView] = useState<'variables' | 'data'>('variables');
  const [searchFilter, setSearchFilter] = useState('');
  const [isVariableSearchOpen, setIsVariableSearchOpen] = useState(false);
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [saveToast, setSaveToast] = useState<string | null>(null);

  // Sync state if store updates dataset
  useEffect(() => {
    if (initialDataset) {
      setDataset(initialDataset);
    }
  }, [initialDataset]);

  // Auto-detect missing value marker
  const detectedMarker = useMemo(() => {
    if (!dataset?.rows) return '';
    for (const row of dataset.rows) {
      for (const val of row || []) {
        if (val === -99 || val === '-99') return '-99';
      }
    }
    return '';
  }, [dataset?.rows]);

  const [missingMarker, setMissingMarker] = useState(detectedMarker || '');
  const [treatment, setTreatment] = useState<'none' | 'listwise' | 'mean'>('none');

  // Save changes to store and backend
  const persistChanges = (updated: ParsedDataset) => {
    setDataset(updated);
    if (currentStudyId) {
      setStudyDataset(currentStudyId, updated);
      touchStudy(currentStudyId);
      if (activeStudy?.path) {
        const headers = updated.variables.map(v => v.name);
        api.saveProjectDataJson(activeStudy.path, updated.filename, headers, updated.rows)
          .catch(err => console.warn('Failed auto-saving dataset:', err));
      }
    }
  };

  const applyMissingSettings = (marker: string, treat: 'none' | 'listwise' | 'mean') => {
    if (!dataset) return;
    const headers = dataset.variables.map(v => v.name);
    const reprocessed = processData(dataset.filename, headers, dataset.rows, {
      missingValueMarker: marker,
      treatment: treat
    });

    const currentVarsMap = new Map(dataset.variables.map(v => [v.name, v]));
    const mergedVars = reprocessed.variables.map(v => {
      const existing = currentVarsMap.get(v.name);
      if (existing) {
        return {
          ...v,
          selected: existing.selected,
          scaleType: v.scaleType,
          name: existing.name
        };
      }
      return v;
    });

    const updated: ParsedDataset = {
      ...reprocessed,
      filename: dataset.filename,
      variables: mergedVars
    };
    persistChanges(updated);
  };

  const handleMissingMarkerChange = (val: string) => {
    setMissingMarker(val);
    applyMissingSettings(val, treatment);
  };

  const handleTreatmentChange = (val: 'none' | 'listwise' | 'mean') => {
    setTreatment(val);
    applyMissingSettings(missingMarker, val);
  };

  const toggleVariableSelection = (colIdx: number) => {
    if (!dataset) return;
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], selected: !newVars[colIdx].selected };
    persistChanges({ ...dataset, variables: newVars });
  };

  const toggleAllVariables = () => {
    if (!dataset) return;
    const shouldSelect = dataset.variables.some(v => !v.selected);
    persistChanges({
      ...dataset,
      variables: dataset.variables.map(v => ({ ...v, selected: shouldSelect }))
    });
  };

  const setVariableScale = (colIdx: number, scaleType: ParsedVariable['scaleType']) => {
    if (!dataset) return;
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], scaleType };
    persistChanges({ ...dataset, variables: newVars });
  };

  const updateVariableName = (colIdx: number, newName: string) => {
    if (!dataset || !newName.trim()) return;
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], name: newName.trim() };
    persistChanges({ ...dataset, variables: newVars });
    setSaveToast('Variable updated');
    setTimeout(() => setSaveToast(null), 2000);
  };

  // Filter variables
  const filteredVariables = useMemo(() => {
    if (!dataset?.variables) return [];
    if (!searchFilter.trim()) return dataset.variables;
    const q = searchFilter.toLowerCase();
    return dataset.variables.filter(v => 
      v.name.toLowerCase().includes(q) || 
      (v.scaleType && v.scaleType.toLowerCase().includes(q))
    );
  }, [dataset?.variables, searchFilter]);

  // Sort rows for Data view
  const sortedRows = useMemo(() => {
    if (!dataset?.rows) return [];
    if (sortCol === null) return dataset.rows;
    return [...dataset.rows].sort((a, b) => {
      const valA = a[sortCol];
      const valB = b[sortCol];
      if (valA === null || valA === undefined || valA === '') return 1;
      if (valB === null || valB === undefined || valB === '') return -1;
      const numA = Number(valA);
      const numB = Number(valB);
      if (!isNaN(numA) && !isNaN(numB)) {
        return sortDirection === 'asc' ? numA - numB : numB - numA;
      }
      return sortDirection === 'asc' 
        ? String(valA).localeCompare(String(valB)) 
        : String(valB).localeCompare(String(valA));
    });
  }, [dataset?.rows, sortCol, sortDirection]);

  // Dynamically compute descriptive statistics for numeric variables
  const statsMap = useMemo(() => {
    if (!dataset?.rows || !dataset?.variables) return new Map<number, { mean?: number; median?: number; stdDev?: number }>();
    const map = new Map<number, { mean?: number; median?: number; stdDev?: number }>();

    dataset.variables.forEach((_, colIdx) => {
      const vals: number[] = [];
      for (const row of dataset.rows) {
        const val = row[colIdx];
        if (val !== null && val !== undefined && val !== '') {
          const num = Number(val);
          if (!isNaN(num)) {
            vals.push(num);
          }
        }
      }
      if (vals.length > 0) {
        vals.sort((a, b) => a - b);
        const sum = vals.reduce((acc, x) => acc + x, 0);
        const mean = sum / vals.length;
        const median =
          vals.length % 2 === 1
            ? vals[Math.floor(vals.length / 2)]
            : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
        const variance =
          vals.reduce((acc, x) => acc + Math.pow(x - mean, 2), 0) / vals.length;
        const stdDev = Math.sqrt(variance);
        map.set(colIdx, { mean, median, stdDev });
      }
    });
    return map;
  }, [dataset?.rows, dataset?.variables]);

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) {
      if (sortDirection === 'asc') setSortDirection('desc');
      else {
        setSortCol(null);
        setSortDirection('asc');
      }
    } else {
      setSortCol(colIdx);
      setSortDirection('asc');
    }
  };

  if (!dataset) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px', color: 'var(--color-text-secondary)' }}>
        <span className="material-symbols-outlined" style={{ fontSize: '48px', color: 'var(--color-text-muted)', marginBottom: '12px' }}>dataset</span>
        <h3 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 6px 0', color: 'var(--color-text-primary)' }}>No Dataset Loaded</h3>
        <p style={{ fontSize: '13px', margin: 0 }}>Import a dataset into this study from the workspace dashboard to view it here.</p>
      </div>
    );
  }

  const selectedCount = dataset.variables.filter(v => v.selected).length;

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--color-bg-base)' }}>
      {/* ═══ SUB-HEADER / CONTROL BAR ═══ */}
      <div className="subheader" style={{ height: '42px', minHeight: '42px', borderBottom: '1px solid var(--color-border-subtle)', background: 'var(--color-bg-raised)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', userSelect: 'none' }}>
        <div className="subheader__breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 500 }}>
          <span
            className="subheader__breadcrumb-link"
            style={{ cursor: 'pointer', color: 'var(--color-text-secondary)' }}
            onClick={() => {
              if (activeWorkspace) {
                openTab({ type: 'workspace', title: activeWorkspace.name, workspaceId: activeWorkspace.id });
              }
            }}
          >
            {activeWorkspace?.name || 'Workspace'}
          </span>
          <span style={{ color: 'var(--color-text-muted)' }}>/</span>
          <span
            className="subheader__breadcrumb-link"
            style={{ cursor: 'pointer', color: 'var(--color-text-secondary)' }}
            onClick={() => {
              if (activeWorkspace) {
                openTab({ type: 'workspace', title: activeWorkspace.name, workspaceId: activeWorkspace.id });
              }
            }}
          >
            {activeStudy?.name || 'Study'}
          </span>
          <span style={{ color: 'var(--color-text-muted)' }}>/</span>
          <span style={{ color: 'var(--color-accent, #6B4EE6)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span className="material-symbols-outlined" style={{ fontSize: '15px' }}>dataset</span>
            {dataset.filename}
          </span>
        </div>

        {/* Flush Variables | Data Switcher */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
          <button
            type="button"
            onClick={() => setCurrentView('variables')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontWeight: currentView === 'variables' ? 600 : 500,
              color: currentView === 'variables' ? 'var(--color-accent, #6B4EE6)' : 'var(--color-text-muted, #64748B)',
              padding: '4px 8px',
              borderBottom: currentView === 'variables' ? '2px solid var(--color-accent, #6B4EE6)' : '2px solid transparent',
              transition: 'all 0.15s ease',
            }}
          >
            Variables ({dataset.variables.length})
          </button>
          <span style={{ color: '#CBD5E1', fontSize: '12px' }}>|</span>
          <button
            type="button"
            onClick={() => setCurrentView('data')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontWeight: currentView === 'data' ? 600 : 500,
              color: currentView === 'data' ? 'var(--color-accent, #6B4EE6)' : 'var(--color-text-muted, #64748B)',
              padding: '4px 8px',
              borderBottom: currentView === 'data' ? '2px solid var(--color-accent, #6B4EE6)' : '2px solid transparent',
              transition: 'all 0.15s ease',
            }}
          >
            Data Matrix ({dataset.rows.length} rows)
          </button>
        </div>
      </div>

      {/* ═══ VIEW CONTENT ═══ */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {currentView === 'variables' ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Missing Value & Bulk Selection Control Bar */}
            <div style={{ padding: '8px 16px', background: 'var(--color-bg-subtle, #f8fafc)', borderBottom: '1px solid var(--color-border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <button
                  type="button"
                  onClick={toggleAllVariables}
                  className="btn btn-secondary"
                  style={{ fontSize: '12px', padding: '4px 10px', height: '28px' }}
                >
                  {selectedCount === dataset.variables.length ? 'Deselect All' : 'Select All'}
                </button>
                <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                  <strong style={{ color: 'var(--color-text-primary)' }}>{selectedCount}</strong> of {dataset.variables.length} indicators selected for model analysis
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                  <span>Missing Marker:</span>
                  <input
                    type="text"
                    value={missingMarker}
                    onChange={e => handleMissingMarkerChange(e.target.value)}
                    placeholder="e.g. -99"
                    style={{
                      width: '64px',
                      padding: '2px 6px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      border: '1px solid var(--color-border-subtle)',
                      background: 'var(--color-bg-base)',
                      fontSize: '12px',
                      color: 'var(--color-text-primary)'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                  <span>Treatment:</span>
                  <select
                    value={treatment}
                    onChange={e => handleTreatmentChange(e.target.value as any)}
                    style={{
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      border: '1px solid var(--color-border-subtle)',
                      background: 'var(--color-bg-base)',
                      fontSize: '12px',
                      color: 'var(--color-text-primary)',
                      cursor: 'pointer'
                    }}
                  >
                    <option value="none">None (Raw)</option>
                    <option value="mean">Mean Replacement</option>
                    <option value="listwise">Listwise Deletion</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Variables Table */}
            <div style={{ flex: 1, overflow: 'auto' }}>
              <table style={{ width: '100%', minWidth: '960px', tableLayout: 'fixed', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: 'var(--color-bg-raised)', borderBottom: '1px solid var(--color-border-subtle)', position: 'sticky', top: 0, zIndex: 10 }}>
                    <th style={{ padding: '8px 12px', width: '40px' }}>
                      <input 
                        type="checkbox" 
                        checked={selectedCount === dataset.variables.length} 
                        onChange={toggleAllVariables} 
                        style={{ cursor: 'pointer' }}
                      />
                    </th>
                    <th style={{ padding: '6px 12px', width: '220px', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {isVariableSearchOpen ? (
                          <div className="inline-search-wrap" style={{ maxWidth: '160px' }}>
                            <input 
                              autoFocus 
                              className="studies-inline-search" 
                              value={searchFilter} 
                              onChange={e => setSearchFilter(e.target.value)} 
                              onBlur={() => { if (!searchFilter) setIsVariableSearchOpen(false); }} 
                              placeholder="Filter variables…" 
                            />
                            {searchFilter && (
                              <button className="inline-search-clear" type="button" aria-label="Clear variable search" onMouseDown={e => e.preventDefault()} onClick={() => setSearchFilter('')}>×</button>
                            )}
                          </div>
                        ) : (
                          <span>Variable Name</span>
                        )}
                        <button 
                          type="button" 
                          style={{ padding: '2px', borderRadius: 'var(--radius-sm)', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', background: 'transparent', cursor: 'pointer' }} 
                          title="Filter variables" 
                          onClick={() => { setIsVariableSearchOpen(open => !open); if (isVariableSearchOpen) setSearchFilter(''); }}
                        >
                          <span className="material-symbols-outlined" style={{ fontSize: '15px' }}>search</span>
                        </button>
                      </div>
                    </th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', width: '150px' }}>Scale Type</th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', textAlign: 'right', width: '80px' }}>Missing</th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', textAlign: 'right', width: '80px' }}>Mean</th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', textAlign: 'right', width: '80px' }}>Median</th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', textAlign: 'right', width: '80px' }}>Min</th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', textAlign: 'right', width: '80px' }}>Max</th>
                    <th style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--color-text-secondary)', textAlign: 'right', width: '90px' }}>Std. Dev</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredVariables.map((v, i) => {
                    const originalIdx = dataset.variables.findIndex(orig => orig.name === v.name);
                    const idx = originalIdx >= 0 ? originalIdx : i;
                    const missingPct = dataset.rows.length > 0 ? ((v.missingCount / dataset.rows.length) * 100).toFixed(1) : '0.0';
                    const colStats = statsMap.get(idx);

                    return (
                      <tr 
                        key={v.name + i} 
                        style={{ 
                          borderBottom: '1px solid var(--color-border-subtle)',
                          background: v.selected ? 'transparent' : 'var(--color-bg-subtle, rgba(0,0,0,0.015))',
                          opacity: v.selected ? 1 : 0.6
                        }}
                      >
                        <td style={{ padding: '8px 12px' }}>
                          <input 
                            type="checkbox" 
                            checked={v.selected} 
                            onChange={() => toggleVariableSelection(idx)} 
                            style={{ cursor: 'pointer' }}
                          />
                        </td>
                        <td style={{ padding: '6px 12px', width: '220px', maxWidth: '220px', overflow: 'hidden', fontWeight: 500, color: 'var(--color-text-primary)' }}>
                          <EditableCell
                            value={v.name}
                            onChange={(newName) => updateVariableName(idx, newName)}
                          />
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <select
                            value={v.scaleType || 'Metric'}
                            onChange={e => setVariableScale(idx, e.target.value as ParsedVariable['scaleType'])}
                            style={{
                              padding: '2px 6px',
                              borderRadius: '4px',
                              border: '1px solid var(--color-border-subtle)',
                              background: 'var(--color-bg-base)',
                              fontSize: '11px',
                              cursor: 'pointer',
                              color: 'var(--color-text-primary)'
                            }}
                          >
                            <option value="Metric">Continuous (Metric)</option>
                            <option value="Ordinal">Ordinal</option>
                            <option value="Categorical">Nominal (Categorical)</option>
                          </select>
                        </td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: v.missingCount > 0 ? 'var(--color-danger, #ef4444)' : 'var(--color-text-muted)' }}>
                          {v.missingCount} ({missingPct}%)
                        </td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{colStats?.mean !== undefined ? colStats.mean.toFixed(3) : '—'}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{colStats?.median !== undefined ? colStats.median.toFixed(3) : '—'}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{v.min ?? '—'}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{v.max ?? '—'}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{colStats?.stdDev !== undefined ? colStats.stdDev.toFixed(3) : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          /* Data Matrix View */
          <div style={{ flex: 1, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'right' }}>
              <thead>
                <tr style={{ background: 'var(--color-bg-raised)', borderBottom: '1px solid var(--color-border-subtle)', position: 'sticky', top: 0, zIndex: 10 }}>
                  <th style={{ padding: '6px 10px', textAlign: 'center', width: '50px', color: 'var(--color-text-muted)', borderRight: '1px solid var(--color-border-subtle)' }}>#</th>
                  {dataset.variables.map((v, colIdx) => (
                    <th 
                      key={v.name} 
                      onClick={() => handleSort(colIdx)}
                      style={{ 
                        padding: '6px 12px', 
                        fontWeight: 600, 
                        color: sortCol === colIdx ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        userSelect: 'none'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '4px' }}>
                        <span>{v.name}</span>
                        {sortCol === colIdx && (
                          <span className="material-symbols-outlined" style={{ fontSize: '13px' }}>
                            {sortDirection === 'asc' ? 'arrow_upward' : 'arrow_downward'}
                          </span>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row, rowIdx) => (
                  <tr 
                    key={rowIdx} 
                    style={{ 
                      borderBottom: '1px solid var(--color-border-subtle)',
                      background: rowIdx % 2 === 0 ? 'transparent' : 'var(--color-bg-subtle, rgba(0,0,0,0.015))'
                    }}
                  >
                    <td style={{ padding: '4px 10px', textAlign: 'center', color: 'var(--color-text-muted)', borderRight: '1px solid var(--color-border-subtle)', fontVariantNumeric: 'tabular-nums' }}>
                      {rowIdx + 1}
                    </td>
                    {row.map((val, cellIdx) => (
                      <td key={cellIdx} style={{ padding: '4px 12px', fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-primary)' }}>
                        {val === null || val === undefined || val === '' ? <span style={{ color: 'var(--color-text-muted)' }}>—</span> : String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── Bottom Status Bar ─── */}
      <div style={{ height: '26px', minHeight: '26px', background: 'var(--color-bg-raised)', borderTop: '1px solid var(--color-border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px', fontSize: '11px', color: 'var(--color-text-muted)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span>Dataset: <strong>{dataset.filename}</strong></span>
          <span>Rows: <strong>{dataset.rows.length}</strong></span>
          <span>Variables: <strong>{dataset.variables.length}</strong> ({selectedCount} active)</span>
        </div>
        <div>
          <span>Treatment: {treatment === 'none' ? 'None' : treatment}</span>
        </div>
      </div>

      {/* ─── Toast ─── */}
      {saveToast && (
        <div style={{
          position: 'fixed',
          bottom: '36px',
          right: '24px',
          backgroundColor: '#0f172a',
          color: '#ffffff',
          padding: '8px 16px',
          borderRadius: '8px',
          fontSize: '12px',
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
    </div>
  );
};

export default DatasetView;
