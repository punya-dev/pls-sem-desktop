import React, { useState } from 'react';
import type { ParsedDataset, ParsedVariable } from '../utils/dataset-parser';
import { EditableCell } from './EditableCell';

interface DataManagerModalProps {
  dataset: ParsedDataset;
  onImport: (dataset: ParsedDataset) => void;
  onCancel: () => void;
}

export const DataManagerModal: React.FC<DataManagerModalProps> = ({ dataset: initialDataset, onImport, onCancel }) => {
  const [dataset, setDataset] = useState<ParsedDataset>(initialDataset);
  const [activeTab, setActiveTab] = useState<'variables' | 'data'>('variables');
  const [delimiter, setDelimiter] = useState('Comma (,)');
  const [decimal, setDecimal] = useState('Period (1,000.23)');
  const [encoding, setEncoding] = useState('UTF-8');

  const toggleVariableSelection = (colIdx: number) => {
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], selected: !newVars[colIdx].selected };
    setDataset({ ...dataset, variables: newVars });
  };

  const toggleAllVariables = () => {
    const shouldSelect = dataset.variables.some(variable => !variable.selected);
    setDataset({
      ...dataset,
      variables: dataset.variables.map(variable => ({ ...variable, selected: shouldSelect }))
    });
  };
  
  const setVariableScale = (colIdx: number, scaleType: ParsedVariable['scaleType']) => {
    const newVars = [...dataset.variables];
    newVars[colIdx] = { ...newVars[colIdx], scaleType };
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

  const selectedVarsCount = dataset.variables.filter(v => v.selected).length;

  return (
    <div className="dataset-import-overlay fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[3px]" role="dialog" aria-modal="true" aria-labelledby="import-dataset-title">
      <section className="dataset-import-modal flex h-[min(86vh,820px)] w-[min(84vw,1240px)] min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        
        {/* 1. HEADER */}
        <div className="dataset-import-header flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-3">
            <h2 id="import-dataset-title" className="shrink-0 text-sm font-semibold tracking-tight text-slate-900">Import Dataset</h2>
            <div className="flex min-w-0 items-center gap-2">
              <div className="group relative flex min-w-0 items-center">
                <svg className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-slate-400 transition-colors group-focus-within:text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                <input 
                  type="text" 
                  value={dataset.filename} 
                  onChange={updateFileName}
                  aria-label="Dataset filename"
                  className="h-7 w-52 min-w-0 rounded-md border border-slate-200 bg-slate-50/80 py-0.5 pl-8 pr-7 font-mono text-xs font-medium text-slate-800 shadow-sm transition-colors hover:border-slate-300 focus:border-indigo-600 focus:bg-white focus:ring-1 focus:ring-indigo-600"
                />
                <svg className="pointer-events-none absolute right-2 h-3 w-3 text-slate-400 transition-colors group-hover:text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
              </div>
              <div className="hidden rounded border border-slate-200/80 bg-slate-100/80 px-2 py-0.5 font-mono text-[11px] text-slate-500 sm:block">
                {dataset.rows.length} rows &times; {dataset.variables.length} columns
              </div>
            </div>
          </div>
          <button onClick={onCancel} aria-label="Close import dialog" className="ml-3 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>

        {/* 2. PARSING CONTROL STRIP */}
        <div className="dataset-import-controls flex shrink-0 flex-wrap items-center gap-2.5 border-b border-slate-200 bg-slate-50/90 px-5 py-2.5 text-xs">
          <label className="inline-flex items-center rounded-md border border-slate-200 bg-white py-1 pl-2.5 pr-2 shadow-sm transition-colors hover:border-slate-300 focus-within:border-indigo-600 focus-within:ring-1 focus-within:ring-indigo-600">
            <span className="mr-1.5 text-[11px] font-medium text-slate-400">Delimiter</span>
            <select value={delimiter} onChange={e => setDelimiter(e.target.value)} className="cursor-pointer appearance-none border-0 bg-transparent p-0 pr-4 font-mono text-xs font-medium text-slate-800 outline-none focus:ring-0">
              <option>Comma (,)</option>
              <option>Semicolon (;)</option>
              <option>Tab (\t)</option>
              <option>Pipe (|)</option>
            </select>
          </label>
          
          <label className="inline-flex items-center rounded-md border border-slate-200 bg-white py-1 pl-2.5 pr-2 shadow-sm transition-colors hover:border-slate-300 focus-within:border-indigo-600 focus-within:ring-1 focus-within:ring-indigo-600">
            <span className="mr-1.5 text-[11px] font-medium text-slate-400">Decimal</span>
            <select value={decimal} onChange={e => setDecimal(e.target.value)} className="cursor-pointer appearance-none border-0 bg-transparent p-0 pr-4 text-xs font-medium text-slate-800 outline-none focus:ring-0">
              <option>Period (1,000.23)</option>
              <option>Comma (1.000,23)</option>
            </select>
          </label>
          
          <label className="inline-flex items-center rounded-md border border-slate-200 bg-white py-1 pl-2.5 pr-2 shadow-sm transition-colors hover:border-slate-300 focus-within:border-indigo-600 focus-within:ring-1 focus-within:ring-indigo-600">
            <span className="mr-1.5 text-[11px] font-medium text-slate-400">Encoding</span>
            <select value={encoding} onChange={e => setEncoding(e.target.value)} className="cursor-pointer appearance-none border-0 bg-transparent p-0 pr-4 font-mono text-xs font-medium text-slate-800 outline-none focus:ring-0">
              <option>UTF-8</option>
              <option>UTF-16</option>
              <option>ISO-8859-1</option>
            </select>
          </label>
          
          <div className="inline-flex items-center rounded-md border border-slate-200 bg-white px-2.5 py-1 shadow-sm">
            <span className="mr-1.5 text-[11px] font-medium text-slate-400">Missing</span>
            <div className="flex items-center gap-1.5">
              <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[11px] font-mono border border-slate-200">-99</span>
              <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[11px] font-mono border border-slate-200">NA</span>
            </div>
          </div>
        </div>

        {/* 3. MAIN WORKBENCH BODY */}
        <div className="dataset-import-workbench flex-1 flex flex-col min-h-0 bg-white">
          <div className="dataset-import-tabs flex shrink-0 items-center border-b border-slate-200 px-5 pb-2 pt-3">
            <div className="flex items-center space-x-1 rounded-lg border border-slate-200/80 bg-slate-100/90 p-0.5 text-xs">
            <button 
              className={`flex items-center space-x-1.5 rounded-md px-3 py-1.5 font-medium transition-colors ${activeTab === 'variables' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
              onClick={() => setActiveTab('variables')}
            >
              <svg className={`w-4 h-4 ${activeTab === 'variables' ? 'text-indigo-500' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
              <span>Variable Definitions</span>
              <span className={`px-1.5 py-0.5 rounded-full text-[11px] font-semibold ${activeTab === 'variables' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'}`}>{dataset.variables.length}</span>
            </button>
            <button 
              className={`flex items-center space-x-1.5 rounded-md px-3 py-1.5 font-medium transition-colors ${activeTab === 'data' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
              onClick={() => setActiveTab('data')}
            >
              <svg className={`w-4 h-4 ${activeTab === 'data' ? 'text-indigo-500' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M3 14h18M9 4v16M15 4v16"></path></svg>
              <span>Data Preview</span>
              <span className={`px-1.5 py-0.5 rounded-full text-[11px] font-semibold ${activeTab === 'data' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'}`}>{dataset.rows.length}&times;{dataset.variables.length}</span>
            </button>
            </div>
          </div>

          {activeTab === 'variables' && (
            <div className="flex-1 overflow-y-auto custom-scroll">
              <table className="dataset-import-table w-full text-left border-collapse text-xs">
                <thead className="bg-slate-50/80 sticky top-0 border-b border-slate-100 text-[11px] uppercase tracking-wider text-slate-500 font-semibold z-10">
                  <tr>
                    <th className="w-12 px-6 py-3">
                      <input type="checkbox" aria-label="Select all variables" className="w-3.5 h-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600/30" checked={selectedVarsCount === dataset.variables.length} onChange={toggleAllVariables} />
                    </th>
                    <th className="w-64 px-4 py-3">Variable Name</th>
                    <th className="w-72 px-4 py-3">Measurement Scale</th>
                    <th className="w-24 px-4 py-3 text-right">Min</th>
                    <th className="w-24 px-4 py-3 text-right">Max</th>
                    <th className="w-24 px-4 py-3 text-right">Missing</th>
                    <th className="px-6 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700 font-sans">
                  {dataset.variables.map((v, i) => (
                    <tr key={i} className={`hover:bg-slate-50 transition-colors group ${i % 2 !== 0 ? 'bg-slate-50/40' : ''}`}>
                      <td className="w-12 px-6 py-2.5">
                        <input 
                          type="checkbox" 
                          checked={v.selected}
                          onChange={() => toggleVariableSelection(i)}
                          className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600/30 transition-shadow" 
                        />
                      </td>
                      <td className={`w-64 px-4 py-2.5 font-mono font-medium text-[13px] tracking-tight ${!v.selected ? 'text-slate-400' : 'text-slate-800'}`}>
                        <EditableCell 
                          value={v.name} 
                          onChange={(val) => updateVariableField(i, 'name', val)} 
                          disabled={!v.selected}
                        />
                      </td>
                      <td className="w-72 px-4 py-2.5">
                        <div className="relative inline-flex items-center w-56">
                          <select 
                            value={v.scaleType}
                            onChange={(e) => setVariableScale(i, e.target.value as ParsedVariable['scaleType'])}
                            disabled={!v.selected}
                            className={`inline-flex items-center justify-between w-full px-3 py-1.5 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 rounded-md text-[13px] text-slate-700 transition-colors font-medium appearance-none bg-none outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 cursor-pointer shadow-sm ${!v.selected ? 'opacity-50' : ''}`}
                          >
                            <option value="Metric">Continuous (Metric)</option>
                            <option value="Ordinal">Ordinal</option>
                            <option value="Categorical">Nominal (Categorical)</option>
                          </select>
                          <svg className="w-4 h-4 text-slate-400 shrink-0 ml-1.5 absolute right-3 pointer-events-none" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd"></path></svg>
                        </div>
                      </td>
                      <td className={`w-24 px-4 py-2.5 text-right font-mono text-[13px] ${!v.selected ? 'text-slate-400' : 'text-slate-600'}`}>
                        <EditableCell 
                          type="number"
                          value={v.min ?? ''} 
                          onChange={(val) => updateVariableField(i, 'min', parseFloat(val))} 
                          disabled={!v.selected}
                          className="text-right"
                        />
                      </td>
                      <td className={`w-24 px-4 py-2.5 text-right font-mono text-[13px] ${!v.selected ? 'text-slate-400' : 'text-slate-600'}`}>
                        <EditableCell 
                          type="number"
                          value={v.max ?? ''} 
                          onChange={(val) => updateVariableField(i, 'max', parseFloat(val))} 
                          disabled={!v.selected}
                          className="text-right"
                        />
                      </td>
                      <td className={`w-24 px-4 py-2.5 text-right font-mono text-[13px] ${v.missingCount > 0 ? 'text-amber-600 font-medium' : 'text-slate-400'}`}>
                        {v.missingCount}
                      </td>
                      <td className="px-6 py-2.5"></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === 'data' && (
            <div className="flex-1 overflow-auto custom-scroll font-mono text-xs">
              <table className="dataset-import-table w-full text-left border-collapse border-b border-slate-100">
                <thead className="bg-slate-50 sticky top-0 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500 font-semibold z-10">
                  <tr>
                    <th className="w-16 px-4 py-2.5 text-center bg-slate-100/80 border-r border-slate-200 font-sans text-slate-400">Row #</th>
                    {dataset.variables.map((v, i) => v.selected && (
                      <th key={i} className="px-4 py-2.5 border-r border-slate-100">{v.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700 bg-white">
                  {dataset.rows.slice(0, 100).map((row, rIdx) => (
                    <tr key={rIdx} className={`hover:bg-slate-50 transition-colors ${rIdx % 2 !== 0 ? 'bg-slate-50/40' : ''}`}>
                      <td className="px-4 py-2 text-center bg-slate-50/50 border-r border-slate-100 font-sans text-slate-400 text-xs">{rIdx + 1}</td>
                      {dataset.variables.map((v, cIdx) => v.selected && (
                        <td key={cIdx} className={`px-4 py-2 border-r border-slate-100 ${row[cIdx] == null || row[cIdx] === '' ? 'text-amber-600 bg-amber-50/50 font-semibold' : ''}`}>
                          {row[cIdx] == null || row[cIdx] === '' ? 'NaN' : String(row[cIdx])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="p-4 bg-white text-center text-xs text-slate-400 font-sans sticky bottom-0 border-t border-slate-100">
                Showing first {Math.min(100, dataset.rows.length)} of {dataset.rows.length} observations
              </div>
            </div>
          )}
        </div>

        {/* 4. FOOTER */}
        <div className="dataset-import-footer flex shrink-0 items-center justify-between border-t border-slate-200 bg-slate-50 px-5 py-3">
          <div className="flex items-center space-x-3 text-sm">
            {selectedVarsCount > 0 ? (
              <>
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-emerald-100 text-emerald-600">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7"></path></svg>
                </span>
                <span className="font-medium text-slate-600">{dataset.rows.length} observations ready to import</span>
              </>
            ) : (
              <span className="font-medium text-rose-500">Please select at least one variable</span>
            )}
          </div>
          <div className="flex items-center space-x-3">
            <button 
              onClick={onCancel} 
              className="px-5 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 hover:text-slate-900 transition-colors" 
              type="button"
            >
              Cancel
            </button>
            <button 
              onClick={() => onImport(dataset)}
              disabled={selectedVarsCount === 0}
              className="flex items-center space-x-2 px-5 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 rounded-lg shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed" 
              type="button"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
              </svg>
              <span>Import Dataset</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};
