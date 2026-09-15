import React, { useState, useRef, useMemo } from 'react';
import type { ParsedDataset, ParsedVariable } from '../utils/dataset-parser';
import { processData } from '../utils/dataset-parser';
import { EditableCell } from './EditableCell';

interface DataManagerModalProps {
  dataset: ParsedDataset;
  onImport: (dataset: ParsedDataset) => void;
  onCancel: () => void;
}

export const DataManagerModal: React.FC<DataManagerModalProps> = ({ dataset: initialDataset, onImport, onCancel }) => {
  const rawDatasetRef = useRef<ParsedDataset>(initialDataset);

  const detectedMarker = useMemo(() => {
    for (const row of initialDataset.rows || []) {
      for (const val of row || []) {
        if (val === -99 || val === '-99') return '-99';
      }
    }
    return '';
  }, [initialDataset]);

  const [missingMarker, setMissingMarker] = useState(detectedMarker);
  const [treatment, setTreatment] = useState<'none' | 'listwise' | 'mean'>('mean');
  const [dataset, setDataset] = useState<ParsedDataset>(() => {
    const headers = initialDataset.variables.map(v => v.name);
    return processData(initialDataset.filename, headers, initialDataset.rows, {
      missingValueMarker: detectedMarker,
      treatment: 'mean',
    });
  });
  const [activeTab, setActiveTab] = useState<'variables' | 'data'>('variables');
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  const applyMissingSettings = (marker: string, treat: 'none' | 'listwise' | 'mean') => {
    const raw = rawDatasetRef.current;
    const headers = raw.variables.map(v => v.name);
    const reprocessed = processData(dataset.filename, headers, raw.rows, {
      missingValueMarker: marker,
      treatment: treat,
    });
    const currentVarsMap = new Map(dataset.variables.map(v => [v.name, v]));
    const mergedVars = reprocessed.variables.map(v => {
      const existing = currentVarsMap.get(v.name);
      return existing ? { ...v, selected: existing.selected, name: existing.name } : v;
    });
    setDataset({ ...reprocessed, filename: dataset.filename, variables: mergedVars });
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
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], selected: !newVars[colIdx].selected };
    setDataset({ ...dataset, variables: newVars });
  };

  const toggleAllVariables = () => {
    const allSelected = dataset.variables.every(v => v.selected);
    setDataset({ ...dataset, variables: dataset.variables.map(v => ({ ...v, selected: !allSelected })) });
  };

  const setVariableScale = (colIdx: number, scale: ParsedVariable['scaleType']) => {
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], scaleType: scale };
    setDataset({ ...dataset, variables: newVars });
  };

  const updateVariableField = (colIdx: number, field: 'name' | 'min' | 'max', value: string | number) => {
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], [field]: value };
    setDataset({ ...dataset, variables: newVars });
  };

  const updateFileName = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDataset({ ...dataset, filename: e.target.value });
  };

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    else { setSortCol(colIdx); setSortDirection('asc'); }
  };

  const sortedRows = useMemo(() => {
    if (sortCol === null) return dataset.rows;
    return [...dataset.rows].sort((a, b) => {
      const valA = a[sortCol], valB = b[sortCol];
      if (valA == null || valA === '') return 1;
      if (valB == null || valB === '') return -1;
      const numA = Number(valA), numB = Number(valB);
      if (!isNaN(numA) && !isNaN(numB)) return sortDirection === 'asc' ? numA - numB : numB - numA;
      return sortDirection === 'asc' ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
    });
  }, [dataset.rows, sortCol, sortDirection]);

  const selectedVarsCount = dataset.variables.filter(v => v.selected).length;

  return (
    <div className="modal-overlay active" style={{ display: 'flex', zIndex: 9999 }} role="dialog" aria-modal="true">
      <section className="dm-modal">

        {/* ── Header ── */}
        <div className="dm-header">
          <div className="dm-header__left">
            <span className="material-symbols-outlined" style={{ fontSize: '16px', color: 'var(--color-accent)' }}>table_view</span>
            <input
              type="text"
              value={dataset.filename}
              onChange={updateFileName}
              aria-label="Dataset filename"
              className="dm-filename-input"
            />
            <span className="dm-dim-badge">{dataset.rows.length} × {dataset.variables.length}</span>
          </div>
          <button type="button" className="icon-btn icon-btn--sm" onClick={onCancel} aria-label="Close">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* ── Tab bar + Controls ── */}
        <div className="dm-subbar">
          <div className="dm-tabs">
            <button
              type="button"
              className={`dm-tab ${activeTab === 'variables' ? 'dm-tab--active' : ''}`}
              onClick={() => setActiveTab('variables')}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>view_column</span>
              Variables
              <span className="dm-tab-badge">{dataset.variables.length}</span>
            </button>
            <button
              type="button"
              className={`dm-tab ${activeTab === 'data' ? 'dm-tab--active' : ''}`}
              onClick={() => setActiveTab('data')}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>grid_on</span>
              Data
              <span className="dm-tab-badge">{dataset.rows.length}</span>
            </button>
          </div>

          <div className="dm-controls">
            <label className="dm-control-group">
              <span className="dm-control-label">Missing marker</span>
              <input
                type="text"
                placeholder="e.g. -99"
                value={missingMarker}
                onChange={e => handleMissingMarkerChange(e.target.value)}
                className="dm-control-input"
                title="Values matching this will be treated as missing"
              />
            </label>
            <label className="dm-control-group">
              <span className="dm-control-label">Treatment</span>
              <select
                value={treatment}
                onChange={e => handleTreatmentChange(e.target.value as 'none' | 'listwise' | 'mean')}
                className="dm-control-select"
              >
                <option value="none">Keep as blank</option>
                <option value="listwise">Listwise deletion</option>
                <option value="mean">Mean imputation</option>
              </select>
            </label>
          </div>
        </div>

        {/* ── Variables table ── */}
        {activeTab === 'variables' && (
          <div className="dm-body custom-scroll">
            <table className="dm-table" style={{ minWidth: 640, tableLayout: 'fixed' }}>
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={selectedVarsCount === dataset.variables.length}
                      onChange={toggleAllVariables}
                      className="dm-checkbox"
                    />
                  </th>
                  <th style={{ width: 220 }}>Variable Name</th>
                  <th style={{ width: 170 }}>Measurement Scale</th>
                  <th className="dm-th--num" style={{ width: 70 }}>Min</th>
                  <th className="dm-th--num" style={{ width: 70 }}>Max</th>
                  <th className="dm-th--num" style={{ width: 70 }}>Missing</th>
                </tr>
              </thead>
              <tbody>
                {dataset.variables.map((v, i) => (
                  <tr key={i} className={!v.selected ? 'dm-row--deselected' : ''}>
                    <td>
                      <input
                        type="checkbox"
                        checked={v.selected}
                        onChange={() => toggleVariableSelection(i)}
                        className="dm-checkbox"
                      />
                    </td>
                    <td className="dm-cell--mono">
                      <EditableCell value={v.name} onChange={val => updateVariableField(i, 'name', val)} disabled={!v.selected} />
                    </td>
                    <td>
                      <select
                        value={v.scaleType}
                        onChange={e => setVariableScale(i, e.target.value as ParsedVariable['scaleType'])}
                        disabled={!v.selected}
                        className="dm-scale-select"
                      >
                        <option value="Metric">Continuous (Metric)</option>
                        <option value="Ordinal">Ordinal</option>
                        <option value="Categorical">Nominal (Categorical)</option>
                      </select>
                    </td>
                    <td className="dm-cell--num">
                      <EditableCell type="number" value={v.min ?? ''} onChange={val => updateVariableField(i, 'min', parseFloat(val))} disabled={!v.selected} className="text-right" />
                    </td>
                    <td className="dm-cell--num">
                      <EditableCell type="number" value={v.max ?? ''} onChange={val => updateVariableField(i, 'max', parseFloat(val))} disabled={!v.selected} className="text-right" />
                    </td>
                    <td className={`dm-cell--num ${v.missingCount > 0 ? 'dm-cell--warning' : 'dm-cell--muted'}`}>
                      {v.missingCount}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Data preview table ── */}
        {activeTab === 'data' && (
          <div className="dm-body dm-body--mono custom-scroll">
            <table className="dm-table">
              <thead>
                <tr>
                  <th className="dm-th--row">#</th>
                  {dataset.variables.map((v, i) => v.selected && (
                    <th key={i} onClick={() => handleSort(i)} className="dm-th--sortable" title="Click to sort">
                      {v.name}
                      <span className="dm-sort-icon material-symbols-outlined">
                        {sortCol === i ? (sortDirection === 'asc' ? 'arrow_upward' : 'arrow_downward') : 'unfold_more'}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRows.slice(0, 100).map((row, rIdx) => (
                  <tr key={rIdx}>
                    <td className="dm-td--row">{rIdx + 1}</td>
                    {dataset.variables.map((v, cIdx) => v.selected && (
                      <td key={cIdx} className={row[cIdx] == null || row[cIdx] === '' ? 'dm-cell--missing' : ''}>
                        {row[cIdx] == null || row[cIdx] === '' ? 'NA' : String(row[cIdx])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="dm-data-footer">
              Showing {Math.min(100, sortedRows.length)} of {sortedRows.length} rows
              {sortCol !== null && ` — sorted by ${dataset.variables[sortCol]?.name} ${sortDirection}`}
            </div>
          </div>
        )}

        {/* ── Footer ── */}
        <div className="dm-footer">
          <div className="dm-footer__status">
            {selectedVarsCount > 0 ? (
              <><span className="material-symbols-outlined" style={{ fontSize: '14px', color: '#059669' }}>check_circle</span>
              <span>{selectedVarsCount} variable{selectedVarsCount !== 1 ? 's' : ''} · {dataset.rows.length} observations ready</span></>
            ) : (
              <span style={{ color: '#ef4444' }}>Select at least one variable to continue</span>
            )}
          </div>
          <div className="dm-footer__actions">
            <button type="button" className="modal__btn-cancel" onClick={onCancel}>Cancel</button>
            <button
              type="button"
              className="modal__btn-create"
              onClick={() => onImport(dataset)}
              disabled={selectedVarsCount === 0}
            >
              Import Dataset
            </button>
          </div>
        </div>

      </section>
    </div>
  );
};

export default DataManagerModal;
