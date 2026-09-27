/**
 * CSPLS Model Canvas Engine
 * Pure Vanilla JS + SVG implementation for professional vector diagramming.
 */

export function initModelCanvas() {
  window.toggleVarCat = function(catEl) {
    const items = catEl.querySelector('.var-items');
    const chevron = catEl.querySelector('.cat-chevron');
    if (items) items.classList.toggle('hidden');
    if (chevron) chevron.classList.toggle('rotated');
  };

  // ─── DOM References ──────────────────────────────────────────────────────
  const svg = document.getElementById('model-svg');
  if (!svg) return;


  const zoomLayer = document.getElementById('zoom-layer');
  const nodesLayer = document.getElementById('nodes-layer');
  const edgesLayer = document.getElementById('edges-layer');
  const guidesLayer = document.getElementById('guides-layer');
  const emptyHint = document.getElementById('canvas-empty-hint');
  const bgRect = document.getElementById('bg-rect');

  // Ensure all arrowhead markers exist in SVG defs
  let defs = svg.querySelector('defs');
  if (!defs) {
    defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    svg.insertBefore(defs, svg.firstChild);
  }
  const requiredMarkers = [
    { id: 'arrow-solid', tag: 'polygon', attrs: { points: '1 2, 9 5, 1 8', fill: 'var(--color-text-primary, #1e293b)' }, refX: '8', refY: '5' },
    { id: 'arrow-solid-selected', tag: 'polygon', attrs: { points: '1 2, 9 5, 1 8', fill: 'var(--color-accent, #6B4EE6)' }, refX: '8', refY: '5' },
    { id: 'arrow-open', tag: 'path', attrs: { d: 'M 2 2 L 8 5 L 2 8', fill: 'none', stroke: 'var(--color-text-primary, #1e293b)', 'stroke-width': '1.5', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, refX: '7', refY: '5' },
    { id: 'arrow-open-selected', tag: 'path', attrs: { d: 'M 2 2 L 8 5 L 2 8', fill: 'none', stroke: 'var(--color-accent, #6B4EE6)', 'stroke-width': '1.5', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, refX: '7', refY: '5' },
    { id: 'arrow-diamond', tag: 'polygon', attrs: { points: '5 1.5, 8.5 5, 5 8.5, 1.5 5', fill: 'var(--color-text-primary, #1e293b)' }, refX: '5', refY: '5' },
    { id: 'arrow-diamond-selected', tag: 'polygon', attrs: { points: '5 1.5, 8.5 5, 5 8.5, 1.5 5', fill: 'var(--color-accent, #6B4EE6)' }, refX: '5', refY: '5' },
    { id: 'arrow-circle', tag: 'circle', attrs: { cx: '5', cy: '5', r: '3', fill: 'var(--color-text-primary, #1e293b)' }, refX: '5', refY: '5' },
    { id: 'arrow-circle-selected', tag: 'circle', attrs: { cx: '5', cy: '5', r: '3', fill: 'var(--color-accent, #6B4EE6)' }, refX: '5', refY: '5' },
  ];
  requiredMarkers.forEach(m => {
    if (!defs.querySelector(`#${m.id}`)) {
      const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
      marker.setAttribute('id', m.id);
      marker.setAttribute('markerWidth', '10');
      marker.setAttribute('markerHeight', '10');
      marker.setAttribute('refX', m.refX);
      marker.setAttribute('refY', m.refY);
      marker.setAttribute('orient', 'auto');
      const child = document.createElementNS('http://www.w3.org/2000/svg', m.tag);
      Object.entries(m.attrs).forEach(([k, v]) => child.setAttribute(k, v));
      marker.appendChild(child);
      defs.appendChild(marker);
    }
  });

  // State
  let nodes = [];
  let edges = [];
  let mode = 'select'; // select, connect
  let transform = { x: 0, y: 0, k: 1 };
  let selectedIds = new Set();
  
  // History
  let history = [];
  let historyIndex = -1;
  let isUndoRedo = false;

  function pushHistory() {
    if (isUndoRedo) return;
    const state = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges))
    };
    if (historyIndex < history.length - 1) {
      history = history.slice(0, historyIndex + 1);
    }
    if (history.length > 0) {
      const last = history[history.length - 1];
      if (JSON.stringify(last) === JSON.stringify(state)) return;
    }
    history.push(state);
    if (history.length > 50) history.shift();
    historyIndex = history.length - 1;
  }
  
  setTimeout(() => pushHistory(), 500);
  
  // Settings
  let isSnapping = true;
  let showGrid = true;

  // Constants
  const NODE_R = 36; // circle radius for latent
  const SNAP_THRESHOLD = 5;

  // Generate ID
  const generateId = () => 'id_' + Math.random().toString(36).substr(2, 9);

  // Update transform
  function applyTransform() {
    hideLatentHoverPopup();
    zoomLayer.setAttribute('transform', `translate(${transform.x}, ${transform.y}) scale(${transform.k})`);
    
    // Update HUD
    const zoomLevelEl = document.getElementById('hud-zoom-level');
    if (zoomLevelEl) zoomLevelEl.textContent = Math.round(transform.k * 100) + '%';
    
    // Scale background pattern
    const pattern = document.getElementById('dot-grid');
    if (pattern) {
      pattern.setAttribute('patternTransform', `translate(${transform.x}, ${transform.y}) scale(${transform.k})`);
    }
  }

  // --- Zoom & Pan ---
  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomIntensity = 0.1;
    const wheel = e.deltaY < 0 ? 1 : -1;
    const zoomFactor = Math.exp(wheel * zoomIntensity);
    
    const newK = Math.max(0.1, Math.min(transform.k * zoomFactor, 3));
    const ratio = newK / transform.k;
    
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const svgPt = pt.matrixTransform(svg.getScreenCTM().inverse());
    
    transform.x = svgPt.x - (svgPt.x - transform.x) * ratio;
    transform.y = svgPt.y - (svgPt.y - transform.y) * ratio;
    transform.k = newK;
    
    applyTransform();
  }, { passive: false });

  let isPanning = false;
  let panStart = { x: 0, y: 0 };
  let panTransformStart = { x: 0, y: 0 };

  svg.addEventListener('mousedown', (e) => {
    // Prevent browser native text selection dragging on canvas
    e.preventDefault();

    if (e.button === 1 || (e.button === 0 && e.shiftKey)) { // Middle click or Shift+Left
      isPanning = true;
      panStart = { x: e.clientX, y: e.clientY };
      panTransformStart = { x: transform.x, y: transform.y };
      svg.style.cursor = 'grabbing';
    } else if (mode === 'text' && (e.target === svg || e.target === bgRect || e.target.tagName === 'svg' || e.target.tagName === 'rect')) {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      const text = prompt('Enter text note:');
      if (text && text.trim()) {
        nodes.push({ id: generateId(), label: text.trim(), x: svgPt.x, y: svgPt.y, isLatent: null, isText: true, bold: false, italic: false, fontSize: 14 });
        render();
      }
      setMode('select');
      updateToolbarUI(document.querySelector('.tb-btn[title*="Select"]'));
    } else if (e.target === svg || e.target === bgRect) {
      clearSelection();
    }
  });

  window.addEventListener('mousemove', (e) => {
    if (isPanning) {
      const dx = e.clientX - panStart.x;
      const dy = e.clientY - panStart.y;
      transform.x = panTransformStart.x + dx;
      transform.y = panTransformStart.y + dy;
      applyTransform();
    }
  });

  window.addEventListener('mouseup', (e) => {
    if (isPanning) {
      isPanning = false;
      svg.style.cursor = 'default';
    }
  });

  // HUD Controls
  document.getElementById('hud-zoom-in')?.addEventListener('click', () => {
    transform.k = Math.min(transform.k * 1.2, 3);
    applyTransform();
  });
  document.getElementById('hud-zoom-out')?.addEventListener('click', () => {
    transform.k = Math.max(transform.k / 1.2, 0.1);
    applyTransform();
  });
  document.getElementById('hud-fit')?.addEventListener('click', () => {
    if (nodes.length === 0) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(n => {
      const halfW = (n.width || (n.isLatent !== false ? 64 : 64)) / 2 + 24;
      const halfH = (n.height || (n.isLatent !== false ? 64 : 24)) / 2 + 24;
      minX = Math.min(minX, n.x - halfW);
      minY = Math.min(minY, n.y - halfH);
      maxX = Math.max(maxX, n.x + halfW);
      maxY = Math.max(maxY, n.y + halfH);
    });
    const rect = svg.getBoundingClientRect();
    const modelWidth = Math.max(maxX - minX, 100);
    const modelHeight = Math.max(maxY - minY, 100);
    const padding = 60;
    const availW = Math.max(rect.width - padding * 2, 100);
    const availH = Math.max(rect.height - padding * 2, 100);
    const scale = Math.min(availW / modelWidth, availH / modelHeight, 1.2);
    const k = Math.max(Math.min(scale, 1.2), 0.2);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    transform = {
      x: (rect.width / 2) - (cx * k),
      y: (rect.height / 2) - (cy * k),
      k: k
    };
    applyTransform();
    const zoomLevelEl = document.getElementById('hud-zoom-level');
    if (zoomLevelEl) zoomLevelEl.textContent = `${Math.round(transform.k * 100)}%`;
  });

  document.getElementById('hud-snap')?.addEventListener('click', function() {
    isSnapping = !isSnapping;
    this.classList.toggle('active', isSnapping);
    if (bgRect) bgRect.style.fill = isSnapping ? 'url(#dot-grid)' : 'none';
  });
  
  document.getElementById('hud-reset')?.addEventListener('click', function() {
    nodes.forEach(n => {
      delete n.fill;
      delete n.stroke;
      delete n.color;
      delete n.fontSize;
      delete n.bold;
      delete n.italic;
      delete n.underline;
      delete n.shape;
      delete n.width;
      delete n.height;
      delete n.textInside;
    });
    edges.forEach(e => {
      delete e.waypoints;
      delete e.strokeWidth;
      delete e.strokeDasharray;
      delete e.arrowhead;
    });
    render();
  });

  document.getElementById('hud-clear')?.addEventListener('click', function() {
    if (confirm("Are you sure you want to clear the entire canvas?")) {
      nodes.length = 0;
      edges.length = 0;
      selectedIds.clear();
      transform.x = 0;
      transform.y = 0;
      transform.k = 1;
      applyTransform();
      const zoomLevelEl = document.getElementById('hud-zoom-level');
      if (zoomLevelEl) zoomLevelEl.textContent = `${Math.round(transform.k * 100)}%`;
      emptyHint.style.display = 'block';
      render();
      pushHistory();
    }
  });

  function undo() {
    if (historyIndex > 0) {
      isUndoRedo = true;
      historyIndex--;
      nodes = JSON.parse(JSON.stringify(history[historyIndex].nodes));
      edges = JSON.parse(JSON.stringify(history[historyIndex].edges));
      selectedIds.clear();
      render();
      isUndoRedo = false;
    }
  }

  function redo() {
    if (historyIndex < history.length - 1) {
      isUndoRedo = true;
      historyIndex++;
      nodes = JSON.parse(JSON.stringify(history[historyIndex].nodes));
      edges = JSON.parse(JSON.stringify(history[historyIndex].edges));
      selectedIds.clear();
      render();
      isUndoRedo = false;
    }
  }

  document.getElementById('btn-undo')?.addEventListener('click', (e) => {
    e.preventDefault();
    undo();
  });

  document.getElementById('btn-redo')?.addEventListener('click', (e) => {
    e.preventDefault();
    redo();
  });

  document.getElementById('btn-delete')?.addEventListener('click', (e) => {
    e.preventDefault();
    deleteSelected();
  });

  document.getElementById('hud-delete')?.addEventListener('click', (e) => {
    e.preventDefault();
    deleteSelected();
  });

  // --- Toolbar Modes ---
  const toolBtns = document.querySelectorAll('.canvas-toolbar .tb-btn');
  toolBtns.forEach(btn => {
    btn.addEventListener('click', function() {
      const title = this.getAttribute('title') || '';
      if (title.includes('Select')) {
        setMode('select');
        updateToolbarUI(this);
      } else if (title.includes('Path Connector')) {
        setMode('connect');
        updateToolbarUI(this);
      } else if (title.includes('Erase')) {
        setMode('erase');
        updateToolbarUI(this);
      } else if (title.includes('Latent variable')) {
        // Prompt for name and plop in center
        setMode('select');
        updateToolbarUI(document.querySelector('.tb-btn[title*="Select"]'));
        
        const name = prompt('Enter Latent Variable Name:');
        if (name && name.trim()) {
          const pt = getSvgCenter();
          addNode(name.trim(), pt.x, pt.y);
        }
      } else if (title.includes('Text Note')) {
        const text = prompt('Enter text note:');
        if (text && text.trim()) {
          const pt = getSvgCenter();
          nodes.push({ id: generateId(), label: text.trim(), x: pt.x, y: pt.y, isLatent: null, isText: true, bold: false, italic: false, fontSize: 14 });
          render();
        }
      } else if (title.includes('Add Comment')) {
        const text = prompt('Enter Comment:');
        if (text && text.trim()) {
          const pt = getSvgCenter();
          nodes.push({ id: generateId(), label: text.trim(), x: pt.x, y: pt.y, isText: true });
          emptyHint.style.display = 'none';
          render();
        }
        pushHistory();
      }
    });
  });

  // Auto-Align Model
  document.querySelector('.tb-btn[title="Auto-Align Model"]')?.addEventListener('click', () => {
    // Reset all arrow bends / waypoints
    edges.forEach(e => {
      e.waypoints = [];
      delete e.waypoints;
      e.curved = false;
    });

    const depths = new Map();
    nodes.forEach(n => { if (n.isLatent !== false) depths.set(n.id, 0); });
    
    let changed = true;
    let iterations = 0;
    while(changed && iterations < 100) {
      changed = false;
      iterations++;
      edges.forEach(e => {
        const sourceDepth = depths.get(e.sourceId);
        const targetDepth = depths.get(e.targetId);
        if (sourceDepth !== undefined && targetDepth !== undefined) {
          if (targetDepth <= sourceDepth) {
            depths.set(e.targetId, sourceDepth + 1);
            changed = true;
          }
        }
      });
    }

    const maxDepth = Math.max(0, ...Array.from(depths.values()));
    const columns = Array.from({length: maxDepth + 1}, () => []);
    
    depths.forEach((depth, id) => {
      const node = nodes.find(n => n.id === id);
      if (node) columns[depth].push(node);
    });

    const colWidth = 360;
    const rowHeight = 220;
    
    const center = getSvgCenter();
    const startX = center.x - (columns.length - 1) * colWidth / 2;

    columns.forEach((colNodes, colIdx) => {
      const startY = center.y - (colNodes.length - 1) * rowHeight / 2;
      colNodes.forEach((node, rowIdx) => {
        node.x = startX + (colIdx * colWidth);
        node.y = startY + (rowIdx * rowHeight);
      });
    });

    // Auto-align indicators as well based on column
    columns.forEach((colNodes, colIdx) => {
      colNodes.forEach(node => {
        selectedIds.clear();
        selectedIds.add(node.id);
        if (colIdx === columns.length - 1 && columns.length > 1) {
          alignIndicators('right');
        } else {
          alignIndicators('left');
        }
      });
    });
    
    selectedIds.clear();
    render();
    pushHistory();

    // Automatically center and fit the model within visible boundaries after auto-aligning
    setTimeout(() => {
      document.getElementById('hud-fit')?.click();
    }, 50);
  });

  // Colors and Font Size (Using Global Event Delegation)
  document.addEventListener('color-picker-input', (e) => {
    const { id, color } = e.detail;
    if (id === 'picker-fill') {
      nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fill = color);
      render();
    } else if (id === 'picker-border') {
      nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.stroke = color);
      render();
    } else if (id === 'picker-text') {
      nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.color = color);
      render();
    }
  });

  document.addEventListener('color-picker-closed', (e) => {
    const { id } = e.detail;
    if (id === 'picker-fill' || id === 'picker-border' || id === 'picker-text') {
      pushHistory();
    }
  });

  // Old event listeners removed due to React re-rendering. Now handled via global delegation.

  // Alignment, Style, and Text Format Dropdowns
  document.addEventListener('click', (e) => {
    // Hide all menus first if we click outside a dropdown container
    if (!e.target.closest('.tb-dropdown-container')) {
      document.querySelectorAll('.tb-dropdown-menu.show').forEach(m => m.classList.remove('show'));
    }

    // Toggle specific menu
    const btn = e.target.closest('.tb-dropdown-btn');
    if (btn) {
      const menu = btn.nextElementSibling;
      const isShowing = menu.classList.contains('show');
      document.querySelectorAll('.tb-dropdown-menu.show').forEach(m => m.classList.remove('show'));
      if (!isShowing) {
        menu.classList.add('show');
      }
    }

    // Handle item clicks globally
    const item = e.target.closest('.tb-dropdown-item, .tb-font-btn, [data-edge-action]');
    if (item) {
      const action = item.getAttribute('data-action') || item.getAttribute('data-edge-action');
      if (action) {
        if (action === 'align-top') alignIndicators('top');
        else if (action === 'align-bottom') alignIndicators('bottom');
        else if (action === 'align-left') alignIndicators('left');
        else if (action === 'align-right') alignIndicators('right');
        
        else if (action === 'shape-circle') {
          nodes.filter(n => selectedIds.has(n.id) && !n.isText).forEach(n => n.shape = 'circle');
          render();
        } else if (action === 'shape-rect') {
          nodes.filter(n => selectedIds.has(n.id) && !n.isText).forEach(n => n.shape = 'rect');
          render();
        } else if (action === 'shape-hex') {
          nodes.filter(n => selectedIds.has(n.id) && !n.isText).forEach(n => n.shape = 'hexagon');
          render();
        } else if (action === 'shape-oct') {
          nodes.filter(n => selectedIds.has(n.id) && !n.isText).forEach(n => n.shape = 'octagon');
          render();
        }
        
        else if (action === 'text-bold') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.bold = !n.bold);
          render();
        } else if (action === 'text-italic') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.italic = !n.italic);
          render();
        } else if (action === 'text-underline') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.underline = !n.underline);
          render();
        } else if (action === 'font-inc') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fontSize = (n.fontSize || 14) + 2);
          render();
        } else if (action === 'font-dec') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fontSize = Math.max(6, (n.fontSize || 14) - 2));
          render();
        } else if (action === 'text-increase') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fontSize = (n.fontSize || 14) + 2);
          render();
        } else if (action === 'text-decrease') {
          nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fontSize = Math.max(6, (n.fontSize || 14) - 2));
          render();
        } else if (action === 'text-inside') {
          nodes.filter(n => selectedIds.has(n.id) && !n.isText).forEach(n => {
            n.labelInside = n.labelInside === undefined ? true : !n.labelInside;
          });
          render();
        }
        
        // Edge styling
        else if (action.startsWith('arrowhead-')) {
          edges.filter(edge => selectedIds.has(edge.id)).forEach(edge => edge.arrowhead = action.replace('arrowhead-', ''));
          render();
        } else if (action.startsWith('line-')) {
          const style = action.replace('line-', '');
          edges.filter(edge => selectedIds.has(edge.id)).forEach(edge => {
            edge.curved = false; // Reset curve by default
            if (style === 'solid') edge.strokeDasharray = '';
            if (style === 'dashed') edge.strokeDasharray = '8 8';
            if (style === 'dotted') edge.strokeDasharray = '2 4';
            if (style === 'curved') {
              edge.strokeDasharray = '';
              edge.curved = true;
            }
          });
          render();
        } else if (action.startsWith('weight-')) {
          edges.filter(edge => selectedIds.has(edge.id)).forEach(edge => edge.strokeWidth = parseFloat(action.replace('weight-', '')));
          render();
        }
      }
      // Update UI after any formatting action
      document.dispatchEvent(new CustomEvent('selectionChange'));
      
      if (!e.target.closest('input') && !e.target.closest('.tb-font-size') && !e.target.closest('select') && !e.target.closest('.tb-font-btn')) {
        const menu = item.closest('.tb-dropdown-menu');
        if(menu) menu.classList.remove('show');
      }
    }
  });

  // Global change listener for inputs that might be re-rendered
  document.addEventListener('change', (e) => {
    if (e.target.id === 'input-font-size') {
      let size = parseInt(e.target.value);
      if (!isNaN(size) && size > 0) {
        nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fontSize = size);
        render();
      }
    } else if (e.target.id === 'input-font-family') {
      const family = e.target.value;
      nodes.filter(n => selectedIds.has(n.id)).forEach(n => n.fontFamily = family);
      render();
    }
  });

  function alignIndicators(direction) {
    if (selectedIds.size !== 1) return;
    const parentId = Array.from(selectedIds)[0];
    const parent = nodes.find(n => n.id === parentId);
    if (!parent || !parent.isLatent) return;
    
    const indicators = nodes.filter(n => n.parentId === parentId && !n.isLatent);
    if (indicators.length === 0) return;
    
    const indWidth = 64;
    const indHeight = 24;
    const gap = 16;
    
    let spacing;
    if (direction === 'left' || direction === 'right') {
      spacing = indHeight + gap;
    } else {
      spacing = indWidth + gap;
    }
    
    const offset = (direction === 'top' || direction === 'bottom') ? 140 : 155;
    
    const totalLength = (indicators.length - 1) * spacing;
    const start = -totalLength / 2;
    
    indicators.forEach((ind, idx) => {
      if (direction === 'right') {
        ind.x = parent.x + offset;
        ind.y = parent.y + start + (idx * spacing);
      } else if (direction === 'left') {
        ind.x = parent.x - offset;
        ind.y = parent.y + start + (idx * spacing);
      } else if (direction === 'top') {
        ind.x = parent.x + start + (idx * spacing);
        ind.y = parent.y - offset;
      } else if (direction === 'bottom') {
        ind.x = parent.x + start + (idx * spacing);
        ind.y = parent.y + offset;
      }
    });
    
    render();
  }

  function updateToolbarUI(activeBtn) {
    if (!activeBtn) return;
    toolBtns.forEach(b => b.classList.remove('active'));
    activeBtn.classList.add('active');
  }

  function setMode(newMode) {
    mode = newMode;
    if (mode === 'connect') {
      svg.style.cursor = 'crosshair';
    } else if (mode === 'erase') {
      svg.style.cursor = 'crosshair';
    } else {
      svg.style.cursor = 'default';
    }
  }

  function getSvgCenter() {
    const rect = svg.getBoundingClientRect();
    const pt = svg.createSVGPoint();
    pt.x = rect.width / 2;
    pt.y = rect.height / 2;
    return pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
  }

  // --- Drag & Drop Variables ---
  window.bindVariableDragEvents = () => {
    const varItems = document.querySelectorAll('.var-item');
    varItems.forEach(item => {
      item.setAttribute('draggable', 'true');
    });
  };
  window.bindVariableDragEvents();

  function cleanIndicatorStem(name) {
    if (!name) return '';
    const cleaned = name.replace(/[_\-\s.]*\d+$/i, '').trim();
    return cleaned || name;
  }

  function deriveConstructName(indicatorNames) {
    if (!indicatorNames || indicatorNames.length === 0) return '';
    const stems = indicatorNames.map(cleanIndicatorStem).filter(Boolean);
    if (stems.length === 0) return '';
    
    const first = stems[0].toUpperCase();
    const allMatch = stems.every(s => s.toUpperCase() === first);
    if (allMatch) return first;
    
    // Find longest common prefix
    let prefix = stems[0];
    for (let i = 1; i < stems.length; i++) {
      while (!stems[i].toUpperCase().startsWith(prefix.toUpperCase()) && prefix.length > 0) {
        prefix = prefix.slice(0, -1);
      }
    }
    prefix = prefix.replace(/[_\-\s.]+$/, '').trim();
    if (prefix.length >= 2) return prefix.toUpperCase();
    return first;
  }

  function isDefaultOrDerivedName(label) {
    if (!label) return true;
    const l = label.trim().toUpperCase();
    return l.startsWith('LATENT') || l.startsWith('NEW_CONSTRUCT') || l.startsWith('CONSTRUCT') || l.startsWith('NODE_') || l.startsWith('LV_');
  }

  window.dropModelVariable = (name, clientX, clientY) => {
    if (!name) return;
    
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
    
    // Check if dropped on a latent node
    const targetNode = nodes.find(n => {
      const dx = n.x - svgPt.x;
      const dy = n.y - svgPt.y;
      return Math.sqrt(dx*dx + dy*dy) <= NODE_R;
    });

    if (targetNode) {
      const existingIndicators = nodes.filter(n => !n.isLatent && n.parentId === targetNode.id);
      if (!existingIndicators.some(n => n.label === name)) {
        nodes.push({
          id: generateId(),
          label: name,
          isLatent: false,
          parentId: targetNode.id,
          x: targetNode.x + 155,
          y: targetNode.y + (existingIndicators.length * 40)
        });

        // Automatically refine construct name based on indicators if default
        const allIndNames = [...existingIndicators.map(i => i.label), name];
        const derived = deriveConstructName(allIndNames);
        if (derived && isDefaultOrDerivedName(targetNode.label)) {
          targetNode.label = derived;
        }

        emptyHint.style.display = 'none';
        render();
        pushHistory();
      }
    } else {
      // Dropping onto empty space: create latent node and attach this variable as its indicator
      const stem = deriveConstructName([name]) || name.toUpperCase().replace(/[_\-\s.]*[0-9]+$/, '');
      const newLatent = addNode(stem, svgPt.x, svgPt.y);
      nodes.push({
        id: generateId(),
        label: name,
        isLatent: false,
        parentId: newLatent.id,
        x: newLatent.x + 155,
        y: newLatent.y
      });
      render();
      pushHistory();
    }
  };

  // --- Nodes & Rendering ---
  function addNode(label, x, y) {
    // Avoid exact duplicate names by appending increment
    let finalLabel = label;
    let count = 1;
    while(nodes.some(n => n.label === finalLabel)) {
      finalLabel = label + '_' + count;
      count++;
    }

    const node = { id: generateId(), label: finalLabel, x, y, isLatent: true, type: 'reflective' };
    nodes.push(node);
    emptyHint.style.display = 'none';
    render();
    return node;
  }

  function createNodeShape(node, defaultW, defaultH, defaultFill, defaultStroke, isSelected) {
    let w = node.width || defaultW;
    let h = node.height || defaultH;
    let shape = node.shape || (node.isLatent ? 'circle' : 'rect');
    let fill = node.fill || defaultFill;
    let stroke = node.stroke || defaultStroke;
    let strokeW = '1.5';
    let el;
    
    if (shape === 'rect') {
      el = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      el.setAttribute('x', -w/2);
      el.setAttribute('y', -h/2);
      el.setAttribute('width', w);
      el.setAttribute('height', h);
      el.setAttribute('rx', node.isLatent ? '8' : '2');
    } else if (shape === 'hexagon') {
      el = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      const points = [
        [0, -h/2], [w/2, -h/4], [w/2, h/4],
        [0, h/2], [-w/2, h/4], [-w/2, -h/4]
      ].map(p => p.join(',')).join(' ');
      el.setAttribute('points', points);
    } else if (shape === 'octagon') {
      el = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      const aW = w/2 * 0.414;
      const aH = h/2 * 0.414;
      const points = [
        [-aW, -h/2], [aW, -h/2], [w/2, -aH], [w/2, aH],
        [aW, h/2], [-aW, h/2], [-w/2, aH], [-w/2, -aH]
      ].map(p => p.join(',')).join(' ');
      el.setAttribute('points', points);
    } else { // circle or ellipse
      el = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
      el.setAttribute('rx', w/2);
      el.setAttribute('ry', h/2);
    }
    
    el.setAttribute('fill', fill);
    el.setAttribute('stroke', isSelected ? 'var(--color-accent)' : stroke);
    el.setAttribute('stroke-width', strokeW);
    return el;
  }

  // ── Calculation Results State & Helpers ──────────────────────────
  let activeResults = (typeof window !== 'undefined' && window._canvasActiveResults) || null;

  function setCanvasResults(results) {
    activeResults = results;
    if (typeof window !== 'undefined') {
      window._canvasActiveResults = results;
    }
    render();
  }

  function findConstructKey(node) {
    if (!activeResults || !node) return null;
    const struct = activeResults.structural || {};
    const rel = activeResults.reliability_and_validity || {};
    const names = activeResults.construct_names || {};

    if (struct.r_squared?.[node.id] !== undefined || rel.composite_reliability?.[node.id] !== undefined) {
      return node.id;
    }
    if (node.label) {
      if (struct.r_squared?.[node.label] !== undefined || rel.composite_reliability?.[node.label] !== undefined) {
        return node.label;
      }
      const upper = node.label.toUpperCase();
      if (struct.r_squared?.[upper] !== undefined || rel.composite_reliability?.[upper] !== undefined) {
        return upper;
      }
    }
    for (const [cid, cname] of Object.entries(names)) {
      if (cid === node.id || (node.label && cname && cname.toUpperCase() === node.label.toUpperCase())) {
        return cid;
      }
    }
    return null;
  }

  function getConstructMetrics(node) {
    if (!activeResults || !node) return null;
    const key = findConstructKey(node);
    if (!key) return null;

    const struct = activeResults.structural || {};
    const rel = activeResults.reliability_and_validity || {};
    const names = activeResults.construct_names || {};

    const r2 = struct.r_squared?.[key];
    const r2Adj = struct.r_squared_adj?.[key];
    const cr = rel.composite_reliability?.[key];
    const ave = rel.ave?.[key];
    const alpha = rel.cronbachs_alpha?.[key];

    return {
      key,
      name: node.label || names[key] || key,
      r2: (r2 !== undefined && r2 !== null && !isNaN(Number(r2))) ? Number(r2) : null,
      r2Adj: (r2Adj !== undefined && r2Adj !== null && !isNaN(Number(r2Adj))) ? Number(r2Adj) : null,
      cr: (cr !== undefined && cr !== null && !isNaN(Number(cr))) ? Number(cr) : null,
      ave: (ave !== undefined && ave !== null && !isNaN(Number(ave))) ? Number(ave) : null,
      alpha: (alpha !== undefined && alpha !== null && !isNaN(Number(alpha))) ? Number(alpha) : null,
    };
  }

  function getPathCoefficient(sourceNode, targetNode) {
    if (!activeResults?.structural?.path_coefficients || !sourceNode || !targetNode) return null;
    const paths = activeResults.structural.path_coefficients;
    const sKey = findConstructKey(sourceNode);
    const tKey = findConstructKey(targetNode);

    if (tKey && sKey && paths[tKey]?.[sKey] !== undefined) {
      return Number(paths[tKey][sKey]);
    }
    const sCandidates = [sKey, sourceNode.id, sourceNode.label, sourceNode.label?.toUpperCase()].filter(Boolean);
    const tCandidates = [tKey, targetNode.id, targetNode.label, targetNode.label?.toUpperCase()].filter(Boolean);

    for (const t of tCandidates) {
      if (paths[t]) {
        for (const s of sCandidates) {
          if (paths[t][s] !== undefined) {
            return Number(paths[t][s]);
          }
        }
      }
    }
    return null;
  }

  function getOuterLoading(parentNode, indicatorNode) {
    if (!activeResults?.measurement?.outer_loadings || !parentNode || !indicatorNode) return null;
    const loadings = activeResults.measurement.outer_loadings;
    const indNames = activeResults.indicator_names || {};
    const pKey = findConstructKey(parentNode);

    const pCandidates = [pKey, parentNode.id, parentNode.label, parentNode.label?.toUpperCase()].filter(Boolean);
    const iCandidates = [indicatorNode.id, indicatorNode.label, indicatorNode.label?.toUpperCase(), indicatorNode.label?.toLowerCase()].filter(Boolean);

    for (const p of pCandidates) {
      if (loadings[p]) {
        for (const i of iCandidates) {
          if (loadings[p][i] !== undefined) {
            return Number(loadings[p][i]);
          }
        }
        for (const [iid, iname] of Object.entries(indNames)) {
          if ((iid === indicatorNode.id || iname === indicatorNode.label) && loadings[p][iid] !== undefined) {
            return Number(loadings[p][iid]);
          }
        }
      }
    }
    return null;
  }

  function showLatentHoverPopup(node, metrics) {
    let popupEl = document.getElementById('canvas-latent-popup');
    if (!popupEl) {
      popupEl = document.createElement('div');
      popupEl.id = 'canvas-latent-popup';
      popupEl.className = 'canvas-latent-popup';
      const container = svg.parentElement || document.body;
      container.appendChild(popupEl);
    }

    const fmtVal = (val) => (val !== null && val !== undefined && !isNaN(val)) ? Number(val).toFixed(4) : '—';

    let r2Rows = '';
    if (metrics.r2 !== null) {
      r2Rows = `
        <div class="canvas-latent-popup__item">
          <span class="canvas-latent-popup__label">R²</span>
          <span class="canvas-latent-popup__val highlight">${fmtVal(metrics.r2)}</span>
        </div>
        <div class="canvas-latent-popup__item">
          <span class="canvas-latent-popup__label">R² Adjusted</span>
          <span class="canvas-latent-popup__val">${fmtVal(metrics.r2Adj)}</span>
        </div>
      `;
    }

    popupEl.innerHTML = `
      <div class="canvas-latent-popup__header">
        <span class="canvas-latent-popup__badge">LATENT</span>
        <span class="canvas-latent-popup__title">${metrics.name || 'Construct'}</span>
      </div>
      <div class="canvas-latent-popup__grid">
        ${r2Rows}
        <div class="canvas-latent-popup__item">
          <span class="canvas-latent-popup__label">Composite Reliability</span>
          <span class="canvas-latent-popup__val">${fmtVal(metrics.cr)}</span>
        </div>
        <div class="canvas-latent-popup__item">
          <span class="canvas-latent-popup__label">Avg Variance Extracted</span>
          <span class="canvas-latent-popup__val">${fmtVal(metrics.ave)}</span>
        </div>
        <div class="canvas-latent-popup__item">
          <span class="canvas-latent-popup__label">Cronbach's Alpha (α)</span>
          <span class="canvas-latent-popup__val">${fmtVal(metrics.alpha)}</span>
        </div>
      </div>
    `;

    const CTM = zoomLayer.getScreenCTM();
    if (CTM) {
      const pt = svg.createSVGPoint();
      pt.x = node.x;
      const h = node.height || (NODE_R * 2);
      pt.y = node.y - h / 2;
      const screenPt = pt.matrixTransform(CTM);
      const containerRect = (svg.parentElement || svg).getBoundingClientRect();

      const posX = screenPt.x - containerRect.left;
      const posY = screenPt.y - containerRect.top;

      popupEl.style.left = `${posX}px`;
      
      const flipUnder = (posY - 150) < 0;
      if (flipUnder) {
        popupEl.style.top = `${posY + h + 12}px`;
        popupEl.style.transform = 'translate(-50%, 0) scale(1)';
      } else {
        popupEl.style.top = `${posY - 8}px`;
        popupEl.style.transform = 'translate(-50%, -100%) scale(1)';
      }
    }

    popupEl.style.display = 'block';
    requestAnimationFrame(() => {
      popupEl.classList.add('visible');
    });
  }

  function hideLatentHoverPopup() {
    const popupEl = document.getElementById('canvas-latent-popup');
    if (!popupEl) return;
    popupEl.classList.remove('visible');
    setTimeout(() => {
      if (!popupEl.classList.contains('visible')) {
        popupEl.style.display = 'none';
      }
    }, 160);
  }

  function render() {
    nodesLayer.innerHTML = '';
    edgesLayer.innerHTML = '';
    
    // Edges
    edges.forEach(edge => {
      const source = nodes.find(n => n.id === edge.sourceId);
      const target = nodes.find(n => n.id === edge.targetId);
      if (!source || !target) return;
      
      const { x1, y1, x2, y2 } = getEdgeCoordinates(source, target, edge);
      
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      
      let d = `M ${x1} ${y1}`;
      if (edge.curved) {
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const dx = x2 - x1;
        const dy = y2 - y1;
        const len = Math.sqrt(dx*dx + dy*dy) || 1;
        const cx = mx + (-dy / len) * 40;
        const cy = my + (dx / len) * 40;
        d += ` Q ${cx} ${cy} ${x2} ${y2}`;
      } else {
        if (edge.waypoints && edge.waypoints.length > 0) {
          edge.waypoints.forEach(wp => {
            d += ` L ${wp.x} ${wp.y}`;
          });
        }
        d += ` L ${x2} ${y2}`;
      }
      
      path.setAttribute('d', d);
      path.setAttribute('class', selectedIds.has(edge.id) ? 'edge-path selected' : 'edge-path');
      
      let markerName = 'arrow-solid';
      if (edge.arrowhead) {
        markerName = `arrow-${edge.arrowhead}`;
      }
      if (edge.arrowhead === 'none') markerName = '';
      
      if (markerName) {
        path.setAttribute('marker-end', selectedIds.has(edge.id) ? `url(#${markerName}-selected)` : `url(#${markerName})`);
      } else {
        path.removeAttribute('marker-end');
      }

      path.style.stroke = selectedIds.has(edge.id) ? 'var(--color-accent)' : 'var(--color-text-primary)';
      path.style.strokeWidth = selectedIds.has(edge.id) ? (edge.strokeWidth ? parseInt(edge.strokeWidth)+1 : '3') : (edge.strokeWidth || '2');
      if (edge.strokeDasharray) {
        path.style.strokeDasharray = edge.strokeDasharray;
      } else {
        path.style.strokeDasharray = '';
      }
      
      path.style.fill = 'none';
      path.style.cursor = 'pointer';
      edgesLayer.appendChild(path);
      
      const clickPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      clickPath.setAttribute('d', d);
      clickPath.style.stroke = 'rgba(0,0,0,0.01)';
      clickPath.style.strokeWidth = '16';
      clickPath.style.fill = 'none';
      clickPath.style.cursor = 'pointer';
      
      clickPath.addEventListener('click', (e) => {
        e.stopPropagation();
        if (mode === 'erase') {
          selectedIds.clear();
          selectedIds.add(edge.id);
          deleteSelected();
          return;
        }
        if (mode === 'select') {
          if (!e.shiftKey) clearSelection();
          selectedIds.add(edge.id);
          render();
        }
      });
      clickPath.addEventListener('contextmenu', (e) => showContextMenu(e, edge.id));
      edgesLayer.appendChild(clickPath);

      // Structural path coefficient badge (between latent variables)
      const coef = getPathCoefficient(source, target);
      if (coef !== null && coef !== undefined) {
        let midX = (x1 + x2) / 2;
        let midY = (y1 + y2) / 2;

        if (edge.waypoints && edge.waypoints.length > 0) {
          const numJoints = edge.waypoints.length;
          if (numJoints % 2 === 1) {
            // Odd number of joints (e.g. 1 joint): exact middle joint
            const midIdx = Math.floor(numJoints / 2);
            midX = edge.waypoints[midIdx].x;
            midY = edge.waypoints[midIdx].y;
          } else {
            // Even number of joints: midpoint between the two middle joints
            const idx1 = numJoints / 2 - 1;
            const idx2 = numJoints / 2;
            midX = (edge.waypoints[idx1].x + edge.waypoints[idx2].x) / 2;
            midY = (edge.waypoints[idx1].y + edge.waypoints[idx2].y) / 2;
          }
        } else if (edge.curved) {
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          const dx = x2 - x1;
          const dy = y2 - y1;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          const cx = mx + (-dy / len) * 40;
          const cy = my + (dx / len) * 40;
          midX = 0.25 * x1 + 0.5 * cx + 0.25 * x2;
          midY = 0.25 * y1 + 0.5 * cy + 0.25 * y2;
        } else {
          midX = (x1 + x2) / 2;
          midY = (y1 + y2) / 2;
        }

        const badgeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        badgeG.setAttribute('class', 'edge-result-badge');
        badgeG.setAttribute('transform', `translate(${midX}, ${midY})`);
        badgeG.setAttribute('pointer-events', 'none');

        const textVal = coef.toFixed(3);
        const pillW = Math.max(34, textVal.length * 7.5 + 10);
        const pillH = 18;

        const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bg.setAttribute('x', -pillW / 2);
        bg.setAttribute('y', -pillH / 2);
        bg.setAttribute('width', pillW);
        bg.setAttribute('height', pillH);
        bg.setAttribute('rx', '4');
        bg.setAttribute('fill', 'var(--color-bg-primary, #ffffff)');
        bg.setAttribute('stroke', selectedIds.has(edge.id) ? 'var(--color-accent, #6B4EE6)' : 'var(--color-border-divider, #cbd5e1)');
        bg.setAttribute('stroke-width', '1');
        badgeG.appendChild(bg);

        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('dominant-baseline', 'central');
        txt.setAttribute('font-size', '10.5');
        txt.setAttribute('font-family', 'var(--font-mono, monospace)');
        txt.setAttribute('font-weight', '600');
        txt.setAttribute('fill', 'var(--color-text-primary, #1e293b)');
        txt.textContent = textVal;
        badgeG.appendChild(txt);

        edgesLayer.appendChild(badgeG);
      }
      
      
      // Draw handles if selected
      if (selectedIds.has(edge.id)) {
        if (!edge.curved && edge.waypoints) {
          edge.waypoints.forEach((wp, idx) => {
            const handle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            handle.setAttribute('cx', wp.x);
            handle.setAttribute('cy', wp.y);
            handle.setAttribute('r', 5);
            handle.setAttribute('fill', 'var(--color-accent, #6B4EE6)');
            handle.style.cursor = 'move';
            
            handle.addEventListener('mousedown', (e) => {
              e.stopPropagation();
              draggingWaypoint = { edge, idx };
            });
            edgesLayer.appendChild(handle);
          });
        }
        
        if (!edge.curved) {
          const pts = [{x: x1, y: y1}, ...(edge.waypoints || []), {x: x2, y: y2}];
          for (let i = 0; i < pts.length - 1; i++) {
            const midX = (pts[i].x + pts[i+1].x) / 2;
            const midY = (pts[i].y + pts[i+1].y) / 2;
            const midHandle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            midHandle.setAttribute('cx', midX);
            midHandle.setAttribute('cy', midY);
            midHandle.setAttribute('r', 5);
            midHandle.setAttribute('fill', 'rgba(168,85,247,0.8)');
            midHandle.style.cursor = 'crosshair';
            
            midHandle.addEventListener('mousedown', (e) => {
               e.stopPropagation();
               pendingWaypoint = { edge, idx: i, midX, midY };
            });
            edgesLayer.appendChild(midHandle);
          }
        }
      }
    });

    // Nodes
    nodes.forEach(node => {
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('transform', `translate(${node.x}, ${node.y})`);
      g.setAttribute('class', 'construct-node');
      g.style.cursor = mode === 'select' ? 'move' : (mode === 'connect' ? 'crosshair' : (mode === 'erase' ? 'pointer' : 'default'));

      const isSelected = selectedIds.has(node.id);

      if (node.isLatent) {
        let w = node.width || NODE_R * 2;
        let h = node.height || NODE_R * 2;
        g.appendChild(createNodeShape(node, NODE_R * 2, NODE_R * 2, '#334155', 'none', isSelected));
        
        // Selection box (Dotted shape)
        if (isSelected) {
          const gap = 8;
          const selShape = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          selShape.setAttribute('x', -(w/2 + gap));
          selShape.setAttribute('y', -(h/2 + gap));
          selShape.setAttribute('width', w + gap*2);
          selShape.setAttribute('height', h + gap*2);
          selShape.setAttribute('rx', '12');
          selShape.setAttribute('fill', 'none');
          selShape.setAttribute('stroke', 'var(--color-accent, #6B4EE6)');
          selShape.setAttribute('stroke-width', '1.5');
          selShape.setAttribute('stroke-dasharray', '6 6');
          g.appendChild(selShape);
          
          // Resize handle
          const handle = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          handle.setAttribute('x', w/2 + gap - 4);
          handle.setAttribute('y', h/2 + gap - 4);
          handle.setAttribute('width', '8');
          handle.setAttribute('height', '8');
          handle.setAttribute('fill', 'var(--color-accent, #6B4EE6)');
          handle.style.cursor = 'se-resize';
          handle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            resizingNode = node;
            const pt = svg.createSVGPoint();
            pt.x = e.clientX;
            pt.y = e.clientY;
            const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
            resizeStartWidth = w;
            resizeStartHeight = h;
            resizeStartPt = svgPt;
          });
          g.appendChild(handle);
        }

        // Label
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.textContent = node.label;
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('pointer-events', 'none');
        text.style.userSelect = 'none';
        text.style.webkitUserSelect = 'none';
        
        if (node.textInside) {
          text.setAttribute('y', 5); // visually centered
          const getContrast = (hex) => {
            if (!hex || hex === 'none') return '#ffffff';
            if (hex.startsWith('var')) return '#ffffff'; // Fallback for css vars
            hex = hex.replace('#', '');
            if (hex.length === 3) hex = hex.split('').map(c => c+c).join('');
            const r = parseInt(hex.substr(0, 2), 16) || 0;
            const g = parseInt(hex.substr(2, 2), 16) || 0;
            const b = parseInt(hex.substr(4, 2), 16) || 0;
            const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
            return (yiq >= 128) ? '#000000' : '#ffffff';
          };
          text.setAttribute('fill', node.color || getContrast(node.fill || '#e0e7ff'));
        } else {
          text.setAttribute('y', h/2 + 24);
          text.setAttribute('fill', node.color || 'var(--color-text-primary)');
        }
        text.setAttribute('font-size', node.fontSize || '14');
        if (node.bold) text.setAttribute('font-weight', 'bold');
        else text.setAttribute('font-weight', '600');
        if (node.italic) text.setAttribute('font-style', 'italic');
        if (node.underline) text.setAttribute('text-decoration', 'underline');
        text.setAttribute('font-family', node.fontFamily || 'var(--font-sans)');
        g.appendChild(text);

        // Display R² inside circle for endogenous latent constructs
        const metrics = getConstructMetrics(node);
        if (metrics && metrics.r2 !== null && metrics.r2 !== undefined) {
          const r2Group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
          r2Group.setAttribute('class', 'latent-r2-display');
          r2Group.setAttribute('pointer-events', 'none');

          const r2Val = metrics.r2.toFixed(3);

          if (node.textInside) {
            const r2Text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            r2Text.setAttribute('text-anchor', 'middle');
            r2Text.setAttribute('dominant-baseline', 'central');
            r2Text.setAttribute('y', 19);
            r2Text.setAttribute('font-size', '10.5');
            r2Text.setAttribute('font-weight', '600');
            r2Text.setAttribute('font-family', 'var(--font-mono, monospace)');
            r2Text.setAttribute('fill', '#ffffff');
            r2Text.textContent = `R²: ${r2Val}`;
            r2Group.appendChild(r2Text);
          } else {
            const r2Label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            r2Label.setAttribute('text-anchor', 'middle');
            r2Label.setAttribute('dominant-baseline', 'central');
            r2Label.setAttribute('y', -10);
            r2Label.setAttribute('font-size', '9');
            r2Label.setAttribute('font-weight', '600');
            r2Label.setAttribute('font-family', 'var(--font-sans)');
            r2Label.setAttribute('fill', 'rgba(255, 255, 255, 0.8)');
            r2Label.textContent = 'R²';
            r2Group.appendChild(r2Label);

            const r2Text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            r2Text.setAttribute('text-anchor', 'middle');
            r2Text.setAttribute('dominant-baseline', 'central');
            r2Text.setAttribute('y', 8);
            r2Text.setAttribute('font-size', '12.5');
            r2Text.setAttribute('font-weight', '600');
            r2Text.setAttribute('font-family', 'var(--font-mono, monospace)');
            r2Text.setAttribute('fill', '#ffffff');
            r2Text.textContent = r2Val;
            r2Group.appendChild(r2Text);
          }
          g.appendChild(r2Group);
        }
      } else if (node.isText) {
        const rectBox = node.rectBox || {width: 100, height: 40};
        
        // Background shape for text box
        const shapeEl = createNodeShape(node, rectBox.width, rectBox.height, node.fill || 'transparent', node.stroke || 'transparent', isSelected);
        if (!node.stroke && !isSelected) shapeEl.setAttribute('stroke', 'transparent');
        g.appendChild(shapeEl);

        // Text Note Rendering
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.textContent = node.label;
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dominant-baseline', 'central');
        text.setAttribute('fill', node.color || 'var(--color-text-primary)');
        text.setAttribute('font-size', node.fontSize || '14');
        if (node.bold) text.setAttribute('font-weight', 'bold');
        if (node.italic) text.setAttribute('font-style', 'italic');
        if (node.underline) text.setAttribute('text-decoration', 'underline');
        text.setAttribute('font-family', node.fontFamily || 'var(--font-sans)');
        g.appendChild(text);
        
        if (isSelected) {
          const gap = 8;
          const selShape = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          selShape.setAttribute('x', -(rectBox.width/2 + gap));
          selShape.setAttribute('y', -(rectBox.height/2 + gap));
          selShape.setAttribute('width', rectBox.width + gap*2);
          selShape.setAttribute('height', rectBox.height + gap*2);
          selShape.setAttribute('rx', '4');
          selShape.setAttribute('fill', 'none');
          selShape.setAttribute('stroke', 'var(--color-accent, #6B4EE6)');
          selShape.setAttribute('stroke-width', '2');
          selShape.setAttribute('stroke-dasharray', '6 6');
          g.appendChild(selShape);
          
          // Resize handle
          const handle = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          handle.setAttribute('x', rectBox.width/2 + gap - 4);
          handle.setAttribute('y', rectBox.height/2 + gap - 4);
          handle.setAttribute('width', '8');
          handle.setAttribute('height', '8');
          handle.setAttribute('fill', 'var(--color-accent, #6B4EE6)');
          handle.style.cursor = 'se-resize';
          handle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            resizingNode = node;
            resizeStartWidth = rectBox.width;
            resizeStartHeight = rectBox.height;
            const pt = svg.createSVGPoint();
            pt.x = e.clientX;
            pt.y = e.clientY;
            resizeStartPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
          });
          g.appendChild(handle);
        }
        g.appendChild(text);
      } else {
        // Indicator
        const indWidth = 64;
        const indHeight = 24;
        let w = node.width || indWidth;
        let h = node.height || indHeight;
        
        g.appendChild(createNodeShape(node, indWidth, indHeight, '#fef08a', '#ca8a04', isSelected));

        if (isSelected) {
          const gap = 8;
          const selShape = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          selShape.setAttribute('x', -(w/2 + gap));
          selShape.setAttribute('y', -(h/2 + gap));
          selShape.setAttribute('width', w + gap*2);
          selShape.setAttribute('height', h + gap*2);
          selShape.setAttribute('rx', '4');
          selShape.setAttribute('fill', 'none');
          selShape.setAttribute('stroke', 'var(--color-accent, #6B4EE6)');
          selShape.setAttribute('stroke-width', '2');
          selShape.setAttribute('stroke-dasharray', '6 6');
          g.appendChild(selShape);
          
          // Resize handle
          const handle = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          handle.setAttribute('x', w/2 + gap - 4);
          handle.setAttribute('y', h/2 + gap - 4);
          handle.setAttribute('width', '8');
          handle.setAttribute('height', '8');
          handle.setAttribute('fill', 'var(--color-accent, #6B4EE6)');
          handle.style.cursor = 'se-resize';
          handle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            resizingNode = node;
            const pt = svg.createSVGPoint();
            pt.x = e.clientX;
            pt.y = e.clientY;
            const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
            resizeStartWidth = w;
            resizeStartHeight = h;
            resizeStartPt = svgPt;
          });
          g.appendChild(handle);
        }
        
        const indText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        indText.textContent = node.label;
        indText.setAttribute('y', 4);
        indText.setAttribute('text-anchor', 'middle');
        indText.setAttribute('fill', node.color || '#422006');
        indText.setAttribute('font-size', node.fontSize || '10');
        if (node.bold) indText.setAttribute('font-weight', 'bold');
        if (node.italic) indText.setAttribute('font-style', 'italic');
        if (node.underline) indText.setAttribute('text-decoration', 'underline');
        indText.setAttribute('font-family', node.fontFamily || 'var(--font-mono)');
        g.appendChild(indText);
        
        // Path between parent latent and this indicator
        if (node.parentId) {
          const parent = nodes.find(n => n.id === node.parentId);
          if (parent) {
            const isFormative = parent.type === 'formative';
            const { x1, y1, x2, y2 } = isFormative
              ? getEdgeCoordinates(node, parent, true)
              : getEdgeCoordinates(parent, node, true);
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', `M ${x1} ${y1} L ${x2} ${y2}`);
            path.setAttribute('stroke', '#64748b');
            path.setAttribute('stroke-width', '1.5');
            path.setAttribute('marker-end', 'url(#arrow-solid)');
            edgesLayer.appendChild(path);

            // Measurement outer loading badge
            const loading = getOuterLoading(parent, node);
            if (loading !== null && loading !== undefined) {
              const indMidX = (x1 + x2) / 2;
              const indMidY = (y1 + y2) / 2;

              const badgeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
              badgeG.setAttribute('class', 'edge-result-badge indicator-badge');
              badgeG.setAttribute('transform', `translate(${indMidX}, ${indMidY})`);
              badgeG.setAttribute('pointer-events', 'none');

              const textVal = loading.toFixed(3);
              const pillW = Math.max(30, textVal.length * 6.5 + 8);
              const pillH = 15;

              const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
              bg.setAttribute('x', -pillW / 2);
              bg.setAttribute('y', -pillH / 2);
              bg.setAttribute('width', pillW);
              bg.setAttribute('height', pillH);
              bg.setAttribute('rx', '3');
              bg.setAttribute('fill', 'var(--color-bg-primary, #ffffff)');
              bg.setAttribute('stroke', 'var(--color-border-divider, #cbd5e1)');
              bg.setAttribute('stroke-width', '0.75');
              badgeG.appendChild(bg);

              const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
              txt.setAttribute('text-anchor', 'middle');
              txt.setAttribute('dominant-baseline', 'central');
              txt.setAttribute('font-size', '9.5');
              txt.setAttribute('font-family', 'var(--font-mono, monospace)');
              txt.setAttribute('font-weight', '500');
              txt.setAttribute('fill', 'var(--color-text-secondary, #475569)');
              txt.textContent = textVal;
              badgeG.appendChild(txt);

              edgesLayer.appendChild(badgeG);
            }
          }
        }
      }
      
      // Interaction
      if (node.isLatent) {
        g.addEventListener('pointerenter', () => {
          if (!activeResults) return;
          const m = getConstructMetrics(node);
          if (m) showLatentHoverPopup(node, m);
        });
        g.addEventListener('pointerleave', () => {
          hideLatentHoverPopup();
        });
      }
      g.addEventListener('mousedown', (e) => handleNodeMouseDown(e, node));
      g.addEventListener('contextmenu', (e) => showContextMenu(e, node.id));
      g.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        
        // Inline editing logic
        const input = document.createElement('input');
        input.type = 'text';
        input.value = node.label;
        input.style.position = 'absolute';
        
        // Calculate position based on current transform (approximate)
        const CTM = svg.getScreenCTM();
        const pt = svg.createSVGPoint();
        pt.x = node.x;
        pt.y = node.y;
        const screenPt = pt.matrixTransform(CTM);
        
        input.style.left = `${screenPt.x - 50}px`;
        input.style.top = `${screenPt.y - 15}px`;
        input.style.width = '100px';
        input.style.textAlign = 'center';
        input.style.zIndex = '1000';
        input.style.fontFamily = 'var(--font-sans)';
        input.style.fontSize = '14px';
        
        document.body.appendChild(input);
        input.focus();
        input.select();
        
        const finishEdit = () => {
          if (input.parentNode) {
            const newName = input.value;
            if (newName && newName.trim()) {
              node.label = newName.trim();
              render();
            }
            document.body.removeChild(input);
          }
        };
        
        input.addEventListener('blur', finishEdit);
        input.addEventListener('keydown', (ke) => {
          if (ke.key === 'Enter') finishEdit();
          if (ke.key === 'Escape') {
            if (input.parentNode) document.body.removeChild(input);
          }
        });
      });

      nodesLayer.appendChild(g);
    });

    const nodeFormattingTools = document.getElementById('node-formatting-tools');
    const edgeFormattingTools = document.getElementById('edge-formatting-tools');
    
    if (selectedIds.size === 1) {
      const selectedId = Array.from(selectedIds)[0];
      const selectedNode = nodes.find(n => n.id === selectedId);
      const selectedEdge = edges.find(e => e.id === selectedId);
      
      if (selectedNode) {
        if (nodeFormattingTools) nodeFormattingTools.style.display = 'flex';
        if (edgeFormattingTools) edgeFormattingTools.style.display = 'none';
        const pickerFill = document.getElementById('picker-fill');
        const pickerBorder = document.getElementById('picker-border');
        const pickerText = document.getElementById('picker-text');
        const inputFont = document.getElementById('input-font-size');
        const btnTextInside = document.querySelector('.tb-dropdown-item[data-action="text-inside"]');
        
        if (pickerFill) {
          let defFill = '#334155';
          if (selectedNode.isText) defFill = '#ffffff';
          else if (selectedNode.isLatent === false) defFill = '#fef08a';
          pickerFill.value = selectedNode.fill || defFill;
        }
        if (pickerBorder) {
          let defStroke = 'transparent';
          if (selectedNode.isText) defStroke = '#ffffff';
          else if (selectedNode.isLatent === false) defStroke = '#ca8a04';
          pickerBorder.value = selectedNode.stroke || defStroke;
        }
        if (pickerText) pickerText.value = selectedNode.color || '#1e293b';
        if (inputFont) inputFont.value = selectedNode.fontSize || 14;
        
        if (btnTextInside) {
          if (selectedNode.isLatent !== false && !selectedNode.isText) {
            btnTextInside.style.display = 'flex';
            btnTextInside.innerHTML = `<span class="material-symbols-outlined">vertical_align_center</span> ${selectedNode.labelInside ? 'Move Outside' : 'Move Inside'}`;
          } else {
            btnTextInside.style.display = 'none';
          }
        }
        
        const btnBold = document.querySelector('.tb-font-btn[data-action="text-bold"]');
        const btnItalic = document.querySelector('.tb-font-btn[data-action="text-italic"]');
        const btnUnderline = document.querySelector('.tb-font-btn[data-action="text-underline"]');
        if (btnBold) {
          btnBold.style.background = selectedNode.bold ? 'rgba(79, 70, 229, 0.1)' : 'transparent';
          btnBold.style.color = selectedNode.bold ? '#4f46e5' : 'inherit';
        }
        if (btnItalic) {
          btnItalic.style.background = selectedNode.italic ? 'rgba(79, 70, 229, 0.1)' : 'transparent';
          btnItalic.style.color = selectedNode.italic ? '#4f46e5' : 'inherit';
        }
        if (btnUnderline) {
          btnUnderline.style.background = selectedNode.underline ? 'rgba(79, 70, 229, 0.1)' : 'transparent';
          btnUnderline.style.color = selectedNode.underline ? '#4f46e5' : 'inherit';
        }

        document.querySelectorAll('.tb-font-size-label').forEach(el => {
          el.textContent = (selectedNode.fontSize || 14) + (el.textContent.includes('px') ? 'px' : '');
        });
        
        const inputFontFamily = document.getElementById('input-font-family');
        if (inputFontFamily) {
          inputFontFamily.value = selectedNode.fontFamily || 'Inter';
        }

        if (window.syncColorPickers) {
          window.syncColorPickers(pickerFill?.value, pickerBorder?.value, pickerText?.value);
        }
      } else if (selectedEdge) {
        if (nodeFormattingTools) nodeFormattingTools.style.display = 'none';
        if (edgeFormattingTools) edgeFormattingTools.style.display = 'flex';
        
        // Update active states
        const activeStyle = selectedEdge.curved ? 'curved' : (selectedEdge.strokeDasharray === '8 8' ? 'dashed' : (selectedEdge.strokeDasharray === '2 4' ? 'dotted' : 'solid'));
        const activeArrowhead = selectedEdge.arrowhead || 'solid';
        
        document.querySelectorAll('#edge-formatting-tools .tb-dropdown-item').forEach(item => {
          item.style.background = 'transparent';
          item.style.border = '1px solid transparent';
          item.style.color = '#334155';
          const spans = item.querySelectorAll('span');
          if (spans.length > 0) spans[0].style.color = '#1e293b';
          if (spans.length > 1) spans[1].style.color = '#64748b';
          
          // hide checkmarks
          const checkmark = item.querySelector('.edge-checkmark');
          if (checkmark) checkmark.style.display = 'none';
        });

        const activeLineBtn = document.querySelector(`.tb-dropdown-item[data-edge-action="line-${activeStyle}"]`);
        const activeArrowBtn = document.querySelector(`.tb-dropdown-item[data-edge-action="arrowhead-${activeArrowhead}"]`);
        
        if (activeLineBtn) {
          activeLineBtn.style.background = '#f5f3ff';
          activeLineBtn.style.border = '1px solid #ddd6fe';
          activeLineBtn.style.color = '#4f46e5';
          const spans = activeLineBtn.querySelectorAll('span');
          if (spans.length > 0) spans[0].style.color = '#1e1b4b';
          if (spans.length > 1) spans[1].style.color = '#6366f1';
          const checkmark = activeLineBtn.querySelector('.edge-checkmark');
          if (checkmark) checkmark.style.display = 'block';
        }
        if (activeArrowBtn) {
          activeArrowBtn.style.background = '#f5f3ff';
          activeArrowBtn.style.border = '1px solid #ddd6fe';
          activeArrowBtn.style.color = '#4f46e5';
          const spans = activeArrowBtn.querySelectorAll('span');
          if (spans.length > 0) spans[0].style.color = '#1e1b4b';
          if (spans.length > 1) spans[1].style.color = '#6366f1';
          const checkmark = activeArrowBtn.querySelector('.edge-checkmark');
          if (checkmark) checkmark.style.display = 'block';
        }
      }
    } else {
      if (nodeFormattingTools) nodeFormattingTools.style.display = 'flex';
      if (edgeFormattingTools) edgeFormattingTools.style.display = 'none';
    }
  }

  // --- Node Dragging & Connect Logic ---
  let draggingNode = null;
  let draggingWaypoint = null;
  let pendingWaypoint = null;
  let dragOffset = { x: 0, y: 0 };
  let resizingNode = null;
  let resizeStartWidth = 0;
  let resizeStartHeight = 0;
  let resizeStartPt = null;
  
  let tempConnecting = false;
  let tempLine = null;
  let connectStartNode = null;

  function handleNodeMouseDown(e, node) {
    hideLatentHoverPopup();
    e.stopPropagation();
    e.preventDefault();
    
    if (mode === 'erase') {
      selectedIds.clear();
      selectedIds.add(node.id);
      deleteSelected();
      return;
    }

    if (mode === 'select') {
      if (!e.shiftKey && !selectedIds.has(node.id)) {
        clearSelection();
      }
      selectedIds.add(node.id);
      
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      draggingNode = node;
      dragOffset = { x: svgPt.x - node.x, y: svgPt.y - node.y };
      render();
    } else if (mode === 'connect') {
      tempConnecting = true;
      connectStartNode = node;
      
      tempLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      tempLine.setAttribute('x1', node.x);
      tempLine.setAttribute('y1', node.y);
      tempLine.setAttribute('x2', node.x);
      tempLine.setAttribute('y2', node.y);
      tempLine.setAttribute('stroke', 'var(--color-text-primary)');
      tempLine.setAttribute('stroke-width', '2');
      tempLine.setAttribute('stroke-dasharray', '5 5');
      edgesLayer.appendChild(tempLine);
    }
  }

  window.addEventListener('mousemove', (e) => {
    if (pendingWaypoint) {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      if (Math.abs(svgPt.x - pendingWaypoint.midX) > 2 || Math.abs(svgPt.y - pendingWaypoint.midY) > 2) {
        if (!pendingWaypoint.edge.waypoints) pendingWaypoint.edge.waypoints = [];
        pendingWaypoint.edge.waypoints.splice(pendingWaypoint.idx, 0, { x: pendingWaypoint.midX, y: pendingWaypoint.midY });
        draggingWaypoint = { edge: pendingWaypoint.edge, idx: pendingWaypoint.idx };
        pendingWaypoint = null;
        render();
      }
      return;
    }

    if (draggingWaypoint) {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      draggingWaypoint.edge.waypoints[draggingWaypoint.idx].x = svgPt.x;
      draggingWaypoint.edge.waypoints[draggingWaypoint.idx].y = svgPt.y;
      render();
      return;
    }
    
    if (resizingNode) {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      const dx = svgPt.x - resizeStartPt.x;
      const dy = svgPt.y - resizeStartPt.y;
      
      let newW = Math.max(20, resizeStartWidth + dx * 2);
      let newH = Math.max(20, resizeStartHeight + dy * 2);
      
      guidesLayer.innerHTML = '';
      if (isSnapping) {
        if (Math.abs(newW - newH) < 15) {
          newW = newH = Math.max(newW, newH);
          
          const cx = resizingNode.x;
          const cy = resizingNode.y;
          const r = newW / 2;
          
          let d = `M ${cx - r} ${cy - r} L ${cx + r} ${cy + r} M ${cx - r} ${cy + r} L ${cx + r} ${cy - r}`;
          if (resizingNode.isLatent !== false && (!resizingNode.shape || resizingNode.shape === 'circle')) {
            d += ` M ${cx - r} ${cy} L ${cx + r} ${cy} M ${cx} ${cy - r} L ${cx} ${cy + r}`;
          }
          
          const guide = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          guide.setAttribute('d', d);
          guide.setAttribute('stroke', '#ef4444');
          guide.setAttribute('stroke-width', '1.5');
          guide.setAttribute('stroke-dasharray', '4 4');
          guide.setAttribute('fill', 'none');
          guidesLayer.appendChild(guide);
        }
      }
      
      resizingNode.width = newW;
      resizingNode.height = newH;
      
      if (resizingNode.isText) {
        if (!resizingNode.rectBox) resizingNode.rectBox = {width: 100, height: 40};
        resizingNode.rectBox.width = resizingNode.width;
        resizingNode.rectBox.height = resizingNode.height;
      }
      
      render();
      return;
    }

    if (draggingNode && mode === 'select') {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      let newX = svgPt.x - dragOffset.x;
      let newY = svgPt.y - dragOffset.y;
      
      // Snapping
      guidesLayer.innerHTML = '';
      if (isSnapping) {
        const getBB = (n) => {
          const w = n.width || (n.isLatent !== false ? 64 : 64);
          const h = n.height || (n.isLatent !== false ? 64 : 24);
          return { left: n.x - w/2, right: n.x + w/2, top: n.y - h/2, bottom: n.y + h/2, cx: n.x, cy: n.y };
        };
        
        let snappedX = false;
        let snappedY = false;

        nodes.forEach(n => {
          if (n.id === draggingNode.id) return;
          const bb = getBB(n);
          const activeBB = getBB({ ...draggingNode, x: newX, y: newY });
          
          if (!snappedX) {
            const xs = [bb.cx, bb.left, bb.right];
            const myXs = [activeBB.cx, activeBB.left, activeBB.right];
            for (let target of xs) {
              for (let me of myXs) {
                if (Math.abs(target - me) < SNAP_THRESHOLD) {
                  newX += (target - me);
                  snappedX = true;
                  drawLineGuide(target, -5000, target, 5000);
                  break;
                }
              }
              if (snappedX) break;
            }
          }

          if (!snappedY) {
            const ys = [bb.cy, bb.top, bb.bottom];
            const myYs = [activeBB.cy, activeBB.top, activeBB.bottom];
            for (let target of ys) {
              for (let me of myYs) {
                if (Math.abs(target - me) < SNAP_THRESHOLD) {
                  newY += (target - me);
                  snappedY = true;
                  drawLineGuide(-5000, target, 5000, target);
                  break;
                }
              }
              if (snappedY) break;
            }
          }
        });

        if (!snappedX) {
          for (let n1 of nodes) {
            if (n1.id === draggingNode.id) continue;
            for (let n2 of nodes) {
              if (n2.id === draggingNode.id || n1.id === n2.id) continue;
              const dx = Math.abs(n1.x - n2.x);
              if (dx < 10) continue;
              if (Math.abs(Math.abs(newX - n1.x) - dx) < SNAP_THRESHOLD) {
                newX = newX > n1.x ? n1.x + dx : n1.x - dx;
                snappedX = true;
                drawLineGuide(n2.x, n1.y, newX, n1.y);
                break;
              }
            }
            if (snappedX) break;
          }
        }

        if (!snappedY) {
          for (let n1 of nodes) {
            if (n1.id === draggingNode.id) continue;
            for (let n2 of nodes) {
              if (n2.id === draggingNode.id || n1.id === n2.id) continue;
              const dy = Math.abs(n1.y - n2.y);
              if (dy < 10) continue;
              if (Math.abs(Math.abs(newY - n1.y) - dy) < SNAP_THRESHOLD) {
                newY = newY > n1.y ? n1.y + dy : n1.y - dy;
                snappedY = true;
                drawLineGuide(n1.x, n2.y, n1.x, newY);
                break;
              }
            }
            if (snappedY) break;
          }
        }

        if (!snappedX) {
          const grid = 20;
          const snappedGrid = Math.round(newX / grid) * grid;
          if (Math.abs(newX - snappedGrid) < 5) {
            newX = snappedGrid;
            snappedX = true;
          }
        }
        if (!snappedY) {
          const grid = 20;
          const snappedGrid = Math.round(newY / grid) * grid;
          if (Math.abs(newY - snappedGrid) < 5) {
            newY = snappedGrid;
            snappedY = true;
          }
        }
      }
      
      draggingNode.x = newX;
      draggingNode.y = newY;
      render();
    }
    
    if (tempConnecting && mode === 'connect') {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      tempLine.setAttribute('x2', svgPt.x);
      tempLine.setAttribute('y2', svgPt.y);

      // Illegal connection detection
      const targetNode = nodes.find(n => {
        if (n.id === connectStartNode.id) return false;
        const dx = n.x - svgPt.x;
        const dy = n.y - svgPt.y;
        return Math.sqrt(dx*dx + dy*dy) <= Math.max(NODE_R, 40);
      });

      if (targetNode) {
        const isIllegal = targetNode.isLatent === false || targetNode.isText === true || edges.some(edge => 
          (edge.sourceId === connectStartNode.id && edge.targetId === targetNode.id) ||
          (edge.sourceId === targetNode.id && edge.targetId === connectStartNode.id)
        );
        if (isIllegal) {
          tempLine.setAttribute('stroke', '#ef4444');
        } else {
          tempLine.setAttribute('stroke', 'var(--color-text-primary)');
        }
      } else {
        tempLine.setAttribute('stroke', 'var(--color-text-primary)');
      }
    }
  });

  window.addEventListener('mouseup', (e) => {
    if (pendingWaypoint) {
      pendingWaypoint = null;
    }
    if (draggingWaypoint) {
      draggingWaypoint = null;
      pushHistory();
      return;
    }
    
    if (resizingNode) {
      resizingNode = null;
      guidesLayer.innerHTML = '';
      pushHistory();
      return;
    }
    
    if (draggingNode) {
      draggingNode = null;
      guidesLayer.innerHTML = ''; // clear guides
      pushHistory();
    }
    
    if (tempConnecting) {
      // Find what we dropped on
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      const targetNode = nodes.find(n => {
        if (n.id === connectStartNode.id) return false;
        const dx = n.x - svgPt.x;
        const dy = n.y - svgPt.y;
        return Math.sqrt(dx*dx + dy*dy) <= NODE_R;
      });
      
      if (targetNode && !targetNode.isText && !connectStartNode.isText) {
        let sId = connectStartNode.id;
        let tId = targetNode.id;
        
        // Auto-flip if drawing from Independent to Latent (arrows must point FROM Latent TO Independent)
        if (targetNode.isLatent !== false && connectStartNode.isLatent === false) {
          sId = targetNode.id;
          tId = connectStartNode.id;
        }

        const isIllegal = edges.some(edge => 
          (edge.sourceId === sId && edge.targetId === tId) ||
          (edge.sourceId === tId && edge.targetId === sId)
        );
        
        if (!isIllegal) {
          edges.push({
            id: generateId(),
            sourceId: sId,
            targetId: tId
          });
          render();
          pushHistory();
        }
      }
      
      tempConnecting = false;
      connectStartNode = null;
      if (tempLine) tempLine.remove();
      
      render();
    }
  });

  function drawLineGuide(x1, y1, x2, y2) {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.setAttribute('stroke', '#ef4444'); // Red alignment guide
    line.setAttribute('stroke-width', '1');
    line.setAttribute('stroke-dasharray', '4 4');
    guidesLayer.appendChild(line);
  }

  function clearSelection() {
    selectedIds.clear();
    render();
  }

  // --- Geometry Helpers ---
  function getEdgeCoordinates(source, target, edge = null) {
    let tX = target.x, tY = target.y;
    let sX = source.x, sY = source.y;
    
    if (edge && edge.waypoints && edge.waypoints.length > 0) {
      tX = edge.waypoints[0].x;
      tY = edge.waypoints[0].y;
      sX = edge.waypoints[edge.waypoints.length - 1].x;
      sY = edge.waypoints[edge.waypoints.length - 1].y;
    }
    
    const getIntersectionOffset = (node, ptX, ptY, isTarget) => {
      const dx = ptX - node.x;
      const dy = ptY - node.y;
      const distance = Math.sqrt(dx*dx + dy*dy);
      if (distance === 0) return { x: 0, y: 0 };
      
      const w = node.width || (node.isLatent !== false ? 64 : 64);
      const h = node.height || (node.isLatent !== false ? 64 : 24);
      const shape = node.shape || 'circle';
      const dirX = isTarget ? dx : dx;
      const dirY = isTarget ? dy : dy;
      
      if (node.isLatent !== false && shape === 'circle') {
        const r = w / 2;
        return { x: (dirX / distance) * r, y: (dirY / distance) * (h / 2) };
      } else {
        const rx = w / 2;
        const ry = h / 2;
        if (Math.abs(dirX) * ry > Math.abs(dirY) * rx) {
          return { x: Math.sign(dirX) * rx, y: dirY * (rx / Math.abs(dirX)) };
        } else {
          return { x: dirX * (ry / Math.abs(dirY)), y: Math.sign(dirY) * ry };
        }
      }
    };
    
    const srcOff = getIntersectionOffset(source, tX, tY, false);
    const tgtOff = getIntersectionOffset(target, sX, sY, true);
    
    let x1 = source.x + srcOff.x;
    let y1 = source.y + srcOff.y;
    let x2 = target.x + tgtOff.x;
    let y2 = target.y + tgtOff.y;

    if (edge && edge.curved) {
      // 1st pass: straight line approximation
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const len = Math.sqrt(dx*dx + dy*dy) || 1;
      const mx = (source.x + target.x) / 2;
      const my = (source.y + target.y) / 2;
      const cx = mx - (dy / len) * 40;
      const cy = my + (dx / len) * 40;

      // 2nd pass: intersect from control point
      const newSrcOff = getIntersectionOffset(source, cx, cy, false);
      const newTgtOff = getIntersectionOffset(target, cx, cy, true);
      x1 = source.x + newSrcOff.x;
      y1 = source.y + newSrcOff.y;
      x2 = target.x + newTgtOff.x;
      y2 = target.y + newTgtOff.y;
    }

    return { x1, y1, x2, y2 };
  }

  // --- Context Menu ---
  const contextMenu = document.createElement('div');
  contextMenu.style.position = 'absolute';
  contextMenu.style.background = 'white';
  contextMenu.style.border = '1px solid rgba(0,0,0,0.1)';
  contextMenu.style.borderRadius = '6px';
  contextMenu.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
  contextMenu.style.padding = '4px';
  contextMenu.style.display = 'none';
  contextMenu.style.zIndex = '1000';
  contextMenu.style.minWidth = '120px';
  contextMenu.style.fontFamily = 'var(--font-sans)';
  contextMenu.style.fontSize = '13px';
  document.body.appendChild(contextMenu);

  function hideContextMenu() {
    contextMenu.style.display = 'none';
  }
  
  contextMenu.innerHTML = `
    <div class="ctx-item" id="ctx-duplicate" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
      <span class="material-symbols-outlined" style="font-size: 16px;">content_copy</span> Duplicate
    </div>
    <div class="ctx-item" id="ctx-rename" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
      <span class="material-symbols-outlined" style="font-size: 16px;">edit</span> Rename
    </div>
    <div class="ctx-item" id="ctx-toggle-mode" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
      <span class="material-symbols-outlined" style="font-size: 16px;">swap_horiz</span> Switch Mode
    </div>
    <div class="ctx-item" id="ctx-delete" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px; color: #ef4444;">
      <span class="material-symbols-outlined" style="font-size: 16px;">delete</span> Delete
    </div>
  `;
  
  // Hover effects
  const ctxItems = contextMenu.querySelectorAll('.ctx-item');
  ctxItems.forEach(item => {
    item.addEventListener('mouseenter', () => item.style.backgroundColor = 'rgba(0,0,0,0.04)');
    item.addEventListener('mouseleave', () => item.style.backgroundColor = 'transparent');
  });

  let ctxTargetId = null;

  contextMenu.querySelector('#ctx-delete').addEventListener('click', () => {
    if (ctxTargetId) {
      if (!selectedIds.has(ctxTargetId)) {
        selectedIds.clear();
        selectedIds.add(ctxTargetId);
      }
      deleteSelected();
    }
    hideContextMenu();
  });
  
  contextMenu.querySelector('#ctx-duplicate').addEventListener('click', () => {
    if (ctxTargetId) {
      const node = nodes.find(n => n.id === ctxTargetId);
      if (node) {
        nodes.push({ ...node, id: generateId(), x: node.x + 40, y: node.y + 40 });
        render();
      }
    }
    hideContextMenu();
  });

  contextMenu.querySelector('#ctx-rename').addEventListener('click', () => {
    if (ctxTargetId) {
      const node = nodes.find(n => n.id === ctxTargetId);
      if (node) {
        // Spawn inline edit
        const pt = svg.createSVGPoint();
        pt.x = node.x; pt.y = node.y;
        const screenPt = pt.matrixTransform(zoomLayer.getScreenCTM());
        const input = document.createElement('input');
        input.type = 'text';
        input.value = node.label;
        input.style.position = 'absolute';
        input.style.left = `${screenPt.x - 50}px`;
        input.style.top = `${screenPt.y - 12}px`;
        input.style.width = '100px';
        input.style.textAlign = 'center';
        input.style.zIndex = '1000';
        document.body.appendChild(input);
        input.focus();
        input.select();
        const finishEdit = () => {
          if (input.value.trim()) node.label = input.value.trim();
          if (input.parentNode) document.body.removeChild(input);
          render();
        };
        input.addEventListener('blur', finishEdit);
        input.addEventListener('keydown', (ke) => {
          if (ke.key === 'Enter') finishEdit();
          if (ke.key === 'Escape') if (input.parentNode) document.body.removeChild(input);
        });
      }
    }
    hideContextMenu();
  });

  const ctxToggleMode = contextMenu.querySelector('#ctx-toggle-mode');
  if (ctxToggleMode) {
    ctxToggleMode.addEventListener('click', () => {
      if (ctxTargetId) {
        const node = nodes.find(n => n.id === ctxTargetId);
        if (node && node.isLatent !== false && !node.isText) {
          node.type = node.type === 'formative' ? 'reflective' : 'formative';
          render();
          pushHistory();
        }
      }
      hideContextMenu();
    });
  }

  window.addEventListener('click', hideContextMenu);

  function showContextMenu(e, id) {
    e.preventDefault();
    e.stopPropagation();
    ctxTargetId = id;
    
    // Select the item
    if (!e.shiftKey) clearSelection();
    selectedIds.add(id);
    render();
    
    contextMenu.style.display = 'block';
    
    // Check if it's an edge (no duplicate or rename)
    const isEdge = edges.some(edge => edge.id === id);
    const targetNode = nodes.find(n => n.id === id);
    const isLatent = !isEdge && targetNode && targetNode.isLatent !== false && !targetNode.isText;

    contextMenu.querySelector('#ctx-duplicate').style.display = isEdge ? 'none' : 'flex';
    contextMenu.querySelector('#ctx-rename').style.display = isEdge ? 'none' : 'flex';

    if (ctxToggleMode) {
      if (isLatent) {
        ctxToggleMode.style.display = 'flex';
        const currentMode = targetNode.type === 'formative' ? 'Formative' : 'Reflective';
        const nextMode = targetNode.type === 'formative' ? 'Reflective' : 'Formative';
        ctxToggleMode.innerHTML = `<span class="material-symbols-outlined" style="font-size: 16px;">swap_horiz</span> Make ${nextMode} <span style="font-size:10px; opacity:0.6; margin-left:auto;">(${currentMode})</span>`;
      } else {
        ctxToggleMode.style.display = 'none';
      }
    }
    
    // Position menu
    let x = e.clientX;
    let y = e.clientY;
    if (x + 120 > window.innerWidth) x -= 120;
    if (y + 100 > window.innerHeight) y -= 100;
    contextMenu.style.left = `${x}px`;
    contextMenu.style.top = `${y}px`;
  }

  svg.addEventListener('contextmenu', (e) => {
    if (e.target === svg || e.target === bgRect) {
      e.preventDefault();
      hideContextMenu();
    }
  });

  function deleteSelected() {
    if (selectedIds.size === 0) return;
    const selectedEdges = edges.filter(e => selectedIds.has(e.id));
    const nodesToDelete = new Set(selectedIds);
    
    // Cascade delete indicators if parent construct is deleted
    nodes.forEach(n => {
      if (n.parentId && nodesToDelete.has(n.parentId)) {
        nodesToDelete.add(n.id);
      }
    });

    selectedEdges.forEach(edge => {
      const sourceNode = nodes.find(n => n.id === edge.sourceId);
      if (sourceNode && sourceNode.isLatent === false) {
         nodesToDelete.add(sourceNode.id);
      }
    });
    
    nodes = nodes.filter(n => !nodesToDelete.has(n.id));
    edges = edges.filter(e => !selectedIds.has(e.id) && !nodesToDelete.has(e.sourceId) && !nodesToDelete.has(e.targetId));
    selectedIds.clear();
    
    if (nodes.length === 0) {
      emptyHint.style.display = 'block';
    }
    render();
    pushHistory();
  }

  // Delete key handler
  if (window._canvasKeydownHandler) {
    window.removeEventListener('keydown', window._canvasKeydownHandler);
  }
  window._canvasKeydownHandler = (e) => {
    // Check if target is input/textarea/contentEditable
    const isInput = e.target && (
      e.target.tagName === 'INPUT' || 
      e.target.tagName === 'TEXTAREA' || 
      e.target.isContentEditable ||
      e.target.getAttribute('contenteditable') === 'true'
    );
    if (isInput) return;

    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      e.stopPropagation();
      if (selectedIds.size > 0) {
        deleteSelected();
      }
      return;
    }

    if (!e.metaKey && !e.ctrlKey) {
      if (e.key.toLowerCase() === 'v') {
        setMode('select');
        updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Select"]'));
      } else if (e.key.toLowerCase() === 'p') {
        setMode('connect');
        updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Path Connector"]'));
      } else if (e.key.toLowerCase() === 'e') {
        setMode('erase');
        updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Erase"]'));
      }
    }

    // Classic Undo & Redo shortcuts
    if (e.metaKey || e.ctrlKey) {
      if (e.key.toLowerCase() === 'z') {
        e.preventDefault();
        e.stopPropagation();
        if (e.shiftKey) {
          redo();
        } else {
          undo();
        }
        return;
      }
      if (e.key.toLowerCase() === 'y') {
        e.preventDefault();
        e.stopPropagation();
        redo();
        return;
      }
    }
    
    if (selectedIds.size > 0) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        nodes.filter(n => selectedIds.has(n.id)).forEach(n => { n.bold = !n.bold; });
        render();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'i') {
        e.preventDefault();
        nodes.filter(n => selectedIds.has(n.id)).forEach(n => { n.italic = !n.italic; });
        render();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'u') {
        e.preventDefault();
        nodes.filter(n => selectedIds.has(n.id)).forEach(n => { n.underline = !n.underline; });
        render();
      }
      if (e.key === '=' || e.key === '+') {
        nodes.filter(n => selectedIds.has(n.id)).forEach(n => { n.fontSize = (n.fontSize || 14) + 2; });
        render();
      }
      if (e.key === '-' || e.key === '_') {
        nodes.filter(n => selectedIds.has(n.id)).forEach(n => { n.fontSize = Math.max(8, (n.fontSize || 14) - 2); });
        render();
      }
    }
  };
  window.addEventListener('keydown', window._canvasKeydownHandler);

  function exportModelSpec() {
    const latentNodes = nodes.filter(n => n.isLatent !== false && !n.isText);
    const indicatorNodes = nodes.filter(n => n.isLatent === false && !n.isText);

    const constructs = latentNodes.map(ln => {
      const childInds = indicatorNodes.filter(ind => ind.parentId === ln.id);
      const indicators = childInds.map(ind => ind.id);
      let cname = ln.label;
      if (!cname || isDefaultOrDerivedName(cname)) {
        const derived = deriveConstructName(childInds.map(i => i.label));
        if (derived) cname = derived;
      }
      return {
        id: ln.id,
        name: cname || ln.label || ln.id,
        type: ln.type === 'formative' ? 'formative' : 'reflective',
        indicators
      };
    });

    const indicators = indicatorNodes.map(ind => ({
      id: ind.id,
      column: ind.label
    }));

    const latentIds = new Set(latentNodes.map(ln => ln.id));
    const paths = edges
      .filter(e => latentIds.has(e.sourceId) && latentIds.has(e.targetId))
      .map(e => ({
        from: e.sourceId,
        to: e.targetId
      }));

    return {
      constructs,
      indicators,
      paths
    };
  }

  function getModelCanvasState() {
    return {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
      transform: { ...transform }
    };
  }

  function loadModelCanvasState(state) {
    if (!state) return;
    if (state.nodes && Array.isArray(state.nodes)) {
      nodes = JSON.parse(JSON.stringify(state.nodes));
    }
    if (state.edges && Array.isArray(state.edges)) {
      edges = JSON.parse(JSON.stringify(state.edges));
    }
    if (state.transform) {
      transform = { ...state.transform };
      applyTransform();
    }
    selectedIds.clear();
    if (emptyHint) {
      emptyHint.style.display = nodes.length === 0 ? 'block' : 'none';
    }
    render();
    pushHistory();
  }

  function toggleMeasurementMode(nodeId) {
    const id = nodeId || Array.from(selectedIds)[0];
    if (!id) return;
    const node = nodes.find(n => n.id === id);
    if (node && node.isLatent !== false && !node.isText) {
      node.type = node.type === 'formative' ? 'reflective' : 'formative';
      render();
      pushHistory();
    }
  }

  window.exportModelSpec = exportModelSpec;
  window.getModelCanvasState = getModelCanvasState;
  window.loadModelCanvasState = loadModelCanvasState;
  window.toggleMeasurementMode = toggleMeasurementMode;
  window.deleteSelectedModelPart = deleteSelected;
  window.canvasUndo = undo;
  window.canvasRedo = redo;
  window.setCanvasResults = setCanvasResults;
}

export function setCanvasResults(results) {
  if (typeof window !== 'undefined') {
    window._canvasActiveResults = results;
    if (window.setCanvasResults) {
      window.setCanvasResults(results);
    }
  }
}

export function exportModelSpec() {
  if (typeof window !== 'undefined' && window.exportModelSpec) {
    return window.exportModelSpec();
  }
  return { constructs: [], indicators: [], paths: [] };
}

export function getModelCanvasState() {
  if (typeof window !== 'undefined' && window.getModelCanvasState) {
    return window.getModelCanvasState();
  }
  return null;
}

export function loadModelCanvasState(state) {
  if (typeof window !== 'undefined' && window.loadModelCanvasState) {
    window.loadModelCanvasState(state);
  }
}

export function toggleMeasurementMode(nodeId) {
  if (typeof window !== 'undefined' && window.toggleMeasurementMode) {
    window.toggleMeasurementMode(nodeId);
  }
}

export function deleteSelectedModelPart() {
  if (typeof window !== 'undefined' && window.deleteSelectedModelPart) {
    window.deleteSelectedModelPart();
  }
}

export function canvasUndo() {
  if (typeof window !== 'undefined' && window.canvasUndo) {
    window.canvasUndo();
  }
}

export function canvasRedo() {
  if (typeof window !== 'undefined' && window.canvasRedo) {
    window.canvasRedo();
  }
}

