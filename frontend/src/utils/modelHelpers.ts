export const formatModelType = (type?: string): string => {
  if (!type) return 'PLS-SEM';
  const clean = type.trim().toLowerCase().replace(/[-_\s]+/g, '');
  if (clean === 'pls' || clean === 'plssem') return 'PLS-SEM';
  if (clean === 'cbsem' || clean === 'cb') return 'CB-SEM';
  if (clean === 'regression') return 'Regression';
  return type.toUpperCase();
};

