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

  const { itemName, onConfirm } = deleteConfirmation;

  const handleConfirm = () => {
    onConfirm();
    closeDeleteConfirm();
  };

  return (
    <div
      className="confirm-delete-overlay"
      onClick={closeDeleteConfirm}
    >
      <div
        className="confirm-delete-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="confirm-delete-message">
          {itemName ? (
            <><strong>"{itemName}"</strong> cannot be recovered. Are you sure?</>
          ) : (
            'This cannot be recovered. Are you sure?'
          )}
        </p>

        <div className="confirm-delete-actions">
          <button
            type="button"
            className="confirm-delete-btn confirm-delete-btn--cancel"
            onClick={closeDeleteConfirm}
          >
            Cancel
          </button>
          <button
            type="button"
            className="confirm-delete-btn confirm-delete-btn--delete"
            onClick={handleConfirm}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDeleteModal;
