type ModalListener = (open: boolean) => void;
let modalListener: ModalListener | null = null;

export function registerImportWorkspaceModal(listener: ModalListener) {
  modalListener = listener;
  return () => {
    if (modalListener === listener) {
      modalListener = null;
    }
  };
}

/**
 * Opens the Import Workspace / Project modal.
 */
export function promptOpenWorkspaceFolder(): void {
  if (modalListener) {
    modalListener(true);
  }
}
