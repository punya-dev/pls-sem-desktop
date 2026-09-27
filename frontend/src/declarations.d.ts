declare module 'sav-reader';
declare module '*/utils/model-canvas' {
  const content: any;
  export default content;
  export const initModelCanvas: any;
  export const ModelCanvas: any;
  export const exportModelSpec: () => any;
  export const getModelCanvasState: () => any;
  export const loadModelCanvasState: (state: any) => void;
  export const setCanvasResults: (results: any) => void;
  export const toggleMeasurementMode: (nodeId?: string) => void;
}
declare module '*/utils/results.js' {
  const content: any;
  export default content;
  export const initResults: any;
}
