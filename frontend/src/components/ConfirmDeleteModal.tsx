import React, { useEffect } from 'react';
import { useStore } from '../store';

export const ConfirmDeleteModal: React.FC = () => {
  const { deleteConfirmation, closeDeleteConfirm } = useStore();

  useEffect(() => {
    if (!deleteConfirmation) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeDeleteConfirm();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        deleteConfirmation.onConfirm();
        closeDeleteConfirm();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [deleteConfirmation, closeDeleteConfirm]);

  if (!deleteConfirmation) return null;

  const { title = 'Confirm Deletion', message = 'Are you sure? This cannot be recovered.', itemName, onConfirm } = deleteConfirmation;

  const handleConfirm = () => {
    onConfirm();
    closeDeleteConfirm();
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[3px] animate-in fade-in duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-delete-title"
      onClick={closeDeleteConfirm}
    >
      <div 
        className="w-full max-w-md overflow-hidden rounded-xl border border-slate-200 bg-white p-5 shadow-2xl transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
            <span className="material-symbols-outlined text-xl">delete_forever</span>
          </div>

          <div className="min-w-0 flex-1">
            <h3 id="confirm-delete-title" className="text-sm font-semibold text-slate-900">
              {title}
            </h3>
            
            <p className="mt-1 text-xs text-slate-600 leading-relaxed">
              {message}
            </p>

            {itemName && (
              <div className="mt-2.5 truncate rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 font-mono text-xs text-slate-700">
                {itemName}
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2 border-t border-slate-100 pt-3.5">
          <button
            type="button"
            onClick={closeDeleteConfirm}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-900"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-red-700 active:bg-red-800"
          >
            <span className="material-symbols-outlined text-sm">delete</span>
            <span>Delete Forever</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDeleteModal;
