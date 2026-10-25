/**
 * StatSEM Model Canvas Engine
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
  let moderatingEffects = [];
  let pendingModeratorNode = null;
  let mode = 'select'; // select, connect, moderation, erase
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
      edges: JSON.parse(JSON.stringify(edges)),
      moderatingEffects: JSON.parse(JSON.stringify(moderatingEffects))
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

    try {
      window.dispatchEvent(new CustomEvent('canvas-changed', {
        detail: {
          nodeCount: nodes.length,
          edgeCount: edges.length
        }
      }));
    } catch (e) {}
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
    if (zoomLevelEl && !zoomLevelEl.querySelector('input')) {
      zoomLevelEl.textContent = Math.round(transform.k * 100) + '%';
    }
    
    // Scale background pattern
    const pattern = document.getElementById('dot-grid');
    if (pattern) {
      pattern.setAttribute('patternTransform', `translate(${transform.x}, ${transform.y}) scale(${transform.k})`);
    }
  }

  function getModelCenterOfMass() {
    const validNodes = nodes.filter(n => typeof n.x === 'number' && !isNaN(n.x) && typeof n.y === 'number' && !isNaN(n.y));
    if (validNodes.length === 0) return null;
    let sumX = 0;
    let sumY = 0;
    validNodes.forEach(n => {
      sumX += n.x;
      sumY += n.y;
    });
    return {
      x: sumX / validNodes.length,
      y: sumY / validNodes.length
    };
  }

  function zoomToCenterOfMass(newK) {
    newK = Math.max(0.1, Math.min(newK, 3));
    const rect = svg.getBoundingClientRect();
    const com = getModelCenterOfMass();

    if (com) {
      // Center of mass placed right at the center of the canvas viewport
      transform.x = (rect.width / 2) - (com.x * newK);
      transform.y = (rect.height / 2) - (com.y * newK);
    } else {
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const ratio = newK / transform.k;
      transform.x = centerX - (centerX - transform.x) * ratio;
      transform.y = centerY - (centerY - transform.y) * ratio;
    }
    transform.k = newK;
    applyTransform();
  }

  // --- Zoom & Pan (Trackpad two-finger move to pan, pinch to zoom) ---
  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      // Pinch to zoom (trackpad pinch gesture or Ctrl/Cmd + wheel)
      const zoomIntensity = 0.008;
      const zoomFactor = Math.exp(-e.deltaY * zoomIntensity);
      const newK = Math.max(0.1, Math.min(transform.k * zoomFactor, 3));
      
      const rect = svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const ratio = newK / transform.k;
      transform.x = mouseX - (mouseX - transform.x) * ratio;
      transform.y = mouseY - (mouseY - transform.y) * ratio;
      transform.k = newK;
      applyTransform();

      const zoomLevelEl = document.getElementById('hud-zoom-level');
      if (zoomLevelEl) zoomLevelEl.textContent = `${Math.round(transform.k * 100)}%`;
    } else {
      // Moving two fingers on trackpad or scrolling mouse wheel -> pan canvas
      transform.x -= e.deltaX;
      transform.y -= e.deltaY;
      applyTransform();
    }
  }, { passive: false });

  let isPanning = false;
  let panStart = { x: 0, y: 0 };
  let panTransformStart = { x: 0, y: 0 };
  let isSpacePressed = false;

  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.repeat) {
      const isInput = e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable);
      if (!isInput) {
        isSpacePressed = true;
        svg.style.cursor = 'grab';
      }
    }
  });

  window.addEventListener('keyup', (e) => {
    if (e.code === 'Space') {
      isSpacePressed = false;
      if (!isPanning) {
        svg.style.cursor = 'default';
      }
    }
  });

  let isMarquee = false;
  let marqueeStart = { x: 0, y: 0 };
  let marqueeInitialSelected = new Set();
  let marqueeEl = null;

  svg.addEventListener('mousedown', (e) => {
    // Prevent browser native text selection dragging on canvas
    e.preventDefault();

    if (e.button === 1 || (e.button === 0 && isSpacePressed)) { // Middle click or Space+Left
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
    } else if (mode === 'select' && e.button === 0 && (e.target === svg || e.target === bgRect)) {
      // Marquee drag-to-select on empty canvas
      isMarquee = true;
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      marqueeStart = { x: svgPt.x, y: svgPt.y };
      marqueeInitialSelected = e.shiftKey ? new Set(selectedIds) : new Set();
      if (!e.shiftKey) {
        selectedIds.clear();
      }

      if (!marqueeEl) {
        marqueeEl = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        marqueeEl.setAttribute('class', 'selection-marquee');
        marqueeEl.style.fill = 'rgba(107, 78, 230, 0.12)';
        marqueeEl.style.stroke = 'var(--color-accent, #6B4EE6)';
        marqueeEl.style.strokeWidth = '1.5px';
        marqueeEl.style.strokeDasharray = '4 4';
        marqueeEl.style.pointerEvents = 'none';
      }
      marqueeEl.setAttribute('x', marqueeStart.x);
      marqueeEl.setAttribute('y', marqueeStart.y);
      marqueeEl.setAttribute('width', 0);
      marqueeEl.setAttribute('height', 0);
      guidesLayer.appendChild(marqueeEl);
      render();
    } else if (e.target === svg || e.target === bgRect) {
      if (mode === 'moderation') {
        const pt = svg.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
        let hitEdge = null;
        for (const edge of edges) {
          const sNode = nodes.find(n => n.id === edge.sourceId);
          const tNode = nodes.find(n => n.id === edge.targetId);
          if (!sNode || !tNode || sNode.isLatent === false || tNode.isLatent === false || sNode.isText || tNode.isText) continue;
          const coords = getEdgeCoordinates(sNode, tNode, edge);
          const dist = distToSegment(svgPt.x, svgPt.y, coords.x1, coords.y1, coords.x2, coords.y2);
          if (dist <= 12) {
            hitEdge = edge;
            break;
          }
        }
        if (hitEdge) {
          handleModerationOnEdge(hitEdge);
          return;
        }
      }
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
      return;
    }

    if (isMarquee && marqueeEl) {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());

      const minX = Math.min(marqueeStart.x, svgPt.x);
      const minY = Math.min(marqueeStart.y, svgPt.y);
      const width = Math.abs(svgPt.x - marqueeStart.x);
      const height = Math.abs(svgPt.y - marqueeStart.y);

      marqueeEl.setAttribute('x', minX);
      marqueeEl.setAttribute('y', minY);
      marqueeEl.setAttribute('width', width);
      marqueeEl.setAttribute('height', height);

      selectedIds.clear();
      marqueeInitialSelected.forEach(id => selectedIds.add(id));

      nodes.forEach(n => {
        const nw = n.width || (n.isLatent !== false ? (NODE_R * 2) : 64);
        const nh = n.height || (n.isLatent !== false ? (NODE_R * 2) : 24);
        const nx1 = n.x - nw / 2;
        const ny1 = n.y - nh / 2;
        const nx2 = n.x + nw / 2;
        const ny2 = n.y + nh / 2;

        const intersects = (nx2 >= minX && nx1 <= minX + width && ny2 >= minY && ny1 <= minY + height);
        if (intersects) {
          selectedIds.add(n.id);
        }
      });

      edges.forEach(edge => {
        if (selectedIds.has(edge.sourceId) && selectedIds.has(edge.targetId)) {
          selectedIds.add(edge.id);
        }
      });

      render();
      return;
    }
  });

  window.addEventListener('mouseup', (e) => {
    if (isPanning) {
      isPanning = false;
      svg.style.cursor = isSpacePressed ? 'grab' : 'default';
    }
    if (isMarquee) {
      isMarquee = false;
      if (marqueeEl && marqueeEl.parentNode) {
        marqueeEl.parentNode.removeChild(marqueeEl);
      }
      marqueeEl = null;
      render();
    }
  });

  // HUD Controls
  document.getElementById('hud-zoom-in')?.addEventListener('click', () => {
    zoomToCenterOfMass(transform.k * 1.2);
  });
  document.getElementById('hud-zoom-out')?.addEventListener('click', () => {
    zoomToCenterOfMass(transform.k / 1.2);
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
  });

  const zoomLevelEl = document.getElementById('hud-zoom-level');
  if (zoomLevelEl) {
    zoomLevelEl.title = "Click to edit zoom %";
    zoomLevelEl.addEventListener('click', function(e) {
      if (this.querySelector('input')) return;
      const currentPct = Math.round(transform.k * 100);
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'hud-zoom__level-input';
      input.value = `${currentPct}%`;

      this.innerHTML = '';
      this.appendChild(input);
      input.focus();
      input.select();

      let finished = false;
      const finishZoom = (valToApply) => {
        if (finished) return;
        finished = true;
        if (valToApply !== undefined && !isNaN(valToApply) && valToApply > 0) {
          const clamped = Math.max(10, Math.min(valToApply, 300));
          zoomToCenterOfMass(clamped / 100);
        }
        zoomLevelEl.textContent = `${Math.round(transform.k * 100)}%`;
      };

      input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          ev.stopPropagation();
          const valStr = input.value.replace(/[^0-9.]/g, '');
          const val = parseFloat(valStr);
          finishZoom(val);
        } else if (ev.key === 'Escape') {
          ev.preventDefault();
          ev.stopPropagation();
          finishZoom();
        }
      });
      input.addEventListener('blur', () => {
        const valStr = input.value.replace(/[^0-9.]/g, '');
        const val = parseFloat(valStr);
        finishZoom(val);
      });
    });
  }

  document.getElementById('hud-snap')?.addEventListener('click', function() {
    isSnapping = !isSnapping;
    this.classList.toggle('active', isSnapping);
    if (bgRect) bgRect.style.fill = isSnapping ? 'url(#dot-grid)' : 'none';
  });
  
  function resetModelStyles() {
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
    pushHistory();
    window.dispatchEvent(new CustomEvent('canvas-changed'));
  }

  document.getElementById('hud-reset')?.addEventListener('click', function(e) {
    if (window._customResetStylesHandler) {
      window._customResetStylesHandler(e);
      return;
    }
    resetModelStyles();
  });

  function clearModelCanvas() {
    nodes.length = 0;
    edges.length = 0;
    selectedIds.clear();
    transform.x = 0;
    transform.y = 0;
    transform.k = 1;
    applyTransform();
    const zoomLevelEl = document.getElementById('hud-zoom-level');
    if (zoomLevelEl) zoomLevelEl.textContent = `${Math.round(transform.k * 100)}%`;
    if (emptyHint) emptyHint.style.display = 'block';
    setCanvasResults(null);
    render();
    pushHistory();
    window.dispatchEvent(new CustomEvent('canvas-changed'));
  }

  document.getElementById('hud-clear')?.addEventListener('click', function(e) {
    // If handled by React or custom dialog, stop
    if (window._customClearCanvasHandler) {
      window._customClearCanvasHandler(e);
      return;
    }
    if (confirm("Are you sure you want to clear the entire canvas and results?")) {
      clearModelCanvas();
    }
  });

  function undo() {
    if (historyIndex > 0) {
      isUndoRedo = true;
      historyIndex--;
      nodes = JSON.parse(JSON.stringify(history[historyIndex].nodes));
      edges = JSON.parse(JSON.stringify(history[historyIndex].edges));
      moderatingEffects = JSON.parse(JSON.stringify(history[historyIndex].moderatingEffects || []));
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
      moderatingEffects = JSON.parse(JSON.stringify(history[historyIndex].moderatingEffects || []));
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
      } else if (title.includes('Moderation Effect')) {
        setMode('connect');
        updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Path Connector"]') || this);
        try {
          window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Connect mode active: Drag from a construct to the middle of a path to add moderation.' } }));
        } catch (err) {}
      } else if (title.includes('Latent variable')) {
        // Prompt for name and plop in center
        setMode('select');
        updateToolbarUI(document.querySelector('.tb-btn[title*="Select"]'));
        
        const name = prompt('Enter Latent Variable Name:');
        if (name && name.trim()) {
          const pt = getSvgCenter();
          addNode(name.trim(), pt.x, pt.y);
        }
      } else if (title.includes('Text Note') || this.getAttribute('data-action') === 'add-text-note') {
        const text = prompt('Enter text note:');
        if (text && text.trim()) {
          const pt = getSvgCenter();
          nodes.push({ id: generateId(), label: text.trim(), x: pt.x, y: pt.y, isLatent: null, isText: true, bold: false, italic: false, fontSize: 14 });
          if (emptyHint) emptyHint.style.display = 'none';
          render();
          pushHistory();
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
    
    // Calculate layout coordinates
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

    // Synchronously compute fit & center transform to eliminate model jump/glitch
    if (nodes.length > 0) {
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
    }

    render();
    pushHistory();
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
    if (mode !== 'moderation') {
      pendingModeratorNode = null;
    }
    if (mode === 'connect' || mode === 'moderation') {
      svg.style.cursor = 'crosshair';
    } else if (mode === 'erase') {
      svg.style.cursor = 'crosshair';
    } else {
      svg.style.cursor = 'default';
    }
    render();
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

  window.dropModelVariable = (payload, clientX, clientY) => {
    if (!payload) return;
    
    // Normalize payload to a list of variable names and an optional construct title
    let varList = [];
    let customTitle = '';

    if (Array.isArray(payload)) {
      varList = payload.filter(Boolean).map(String);
    } else if (typeof payload === 'object' && payload !== null) {
      if (Array.isArray(payload.vars)) {
        varList = payload.vars.filter(Boolean).map(String);
      }
      if (payload.name) {
        customTitle = String(payload.name).trim();
      }
    } else if (typeof payload === 'string') {
      const trimmed = payload.trim();
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
          const parsed = JSON.parse(trimmed);
          if (Array.isArray(parsed)) {
            varList = parsed.filter(Boolean).map(String);
          } else if (parsed && typeof parsed === 'object') {
            if (Array.isArray(parsed.vars)) varList = parsed.vars.filter(Boolean).map(String);
            if (parsed.name) customTitle = String(parsed.name).trim();
          }
        } catch (e) {
          varList = [trimmed];
        }
      } else if (trimmed.includes(',')) {
        varList = trimmed.split(',').map(s => s.trim()).filter(Boolean);
      } else {
        varList = [trimmed];
      }
    }

    if (varList.length === 0) return;

    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
    
    // Check if dropped on an existing latent node
    const targetNode = nodes.find(n => {
      if (n.isLatent === false || n.isText) return false;
      const dx = n.x - svgPt.x;
      const dy = n.y - svgPt.y;
      return Math.sqrt(dx*dx + dy*dy) <= NODE_R;
    });

    if (targetNode) {
      const existingIndicators = nodes.filter(n => !n.isLatent && n.parentId === targetNode.id);
      let addedAny = false;
      varList.forEach((name) => {
        if (!existingIndicators.some(n => n.label === name) && !nodes.some(n => n.parentId === targetNode.id && n.label === name)) {
          const countNow = nodes.filter(n => !n.isLatent && n.parentId === targetNode.id).length;
          nodes.push({
            id: generateId(),
            label: name,
            isLatent: false,
            parentId: targetNode.id,
            x: targetNode.x + 155,
            y: targetNode.y + (countNow * 40)
          });
          addedAny = true;
        }
      });

      if (addedAny) {
        // Automatically refine construct name if default or derived
        const allCurrentInds = nodes.filter(n => !n.isLatent && n.parentId === targetNode.id).map(i => i.label);
        const derived = deriveConstructName(allCurrentInds);
        if (derived && isDefaultOrDerivedName(targetNode.label)) {
          targetNode.label = derived;
        }
        emptyHint.style.display = 'none';
        render();
        pushHistory();
      }
    } else {
      // Dropping onto empty space: create latent node and attach all variables as its indicators
      const stem = customTitle || deriveConstructName(varList) || (varList[0] ? varList[0].toUpperCase().replace(/[_\-\s.]*[0-9]+$/, '') : 'NEW_CONSTRUCT');
      const newLatent = addNode(stem, svgPt.x, svgPt.y);

      const indHeight = 24;
      const gap = 16;
      const spacing = indHeight + gap;
      const totalLength = (varList.length - 1) * spacing;
      const start = -totalLength / 2;

      varList.forEach((name, idx) => {
        nodes.push({
          id: generateId(),
          label: name,
          isLatent: false,
          parentId: newLatent.id,
          x: newLatent.x + 155,
          y: newLatent.y + start + (idx * spacing)
        });
      });

      emptyHint.style.display = 'none';
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
    let fill = node.fill;
    let stroke = node.stroke;
    if (!fill || fill === '#334155' || fill === '#1e293b' || fill === '#1e1b4b' || fill === '#e2e8f0' || (typeof fill === 'string' && fill.includes('var(--canvas-latent-fill)'))) {
      fill = defaultFill;
    }
    if (!stroke || stroke === '#1e293b' || stroke === '#475569' || stroke === '#94a3b8' || stroke === 'none' || (typeof stroke === 'string' && stroke.includes('var(--canvas-latent-stroke)'))) {
      stroke = defaultStroke;
    }
    if (node.isLatent === false) {
      if (!node.fill || node.fill === '#fef08a' || node.fill === '#451a03' || (typeof node.fill === 'string' && node.fill.includes('var(--canvas-manifest-fill)'))) {
        fill = defaultFill;
      }
      if (!node.stroke || node.stroke === '#ca8a04' || node.stroke === '#b45309' || (typeof node.stroke === 'string' && node.stroke.includes('var(--canvas-manifest-stroke)'))) {
        stroke = defaultStroke;
      }
    }
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
    el.style.fill = fill;
    el.setAttribute('stroke', isSelected ? 'var(--color-accent)' : stroke);
    el.style.stroke = isSelected ? 'var(--color-accent)' : stroke;
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

  function getModerationDetails(mod) {
    if (!activeResults || !mod) return null;
    const modNode = nodes.find(n => n.id === mod.moderator);
    const sNode = nodes.find(n => n.id === mod.source);
    const tNode = nodes.find(n => n.id === mod.target);
    if (!modNode || !sNode || !tNode) return null;

    const mKey = findConstructKey(modNode) || modNode.id;
    const sKey = findConstructKey(sNode) || sNode.id;
    const tKey = findConstructKey(tNode) || tNode.id;

    const mName = modNode.label || mKey;
    const sName = sNode.label || sKey;
    const tName = tNode.label || tKey;

    // Possible terms for interaction LV (moderator x predictor)
    const termCandidates = [
      `${mName} x ${sName}`,
      `${mKey} x ${sKey}`,
      `${mName.toUpperCase()} x ${sName.toUpperCase()}`,
      `${mKey.toUpperCase()} x ${sKey.toUpperCase()}`,
      `${mName}_x_${sName}`,
      `${mKey}_x_${sKey}`,
      `${sName} x ${mName}`,
      `${sKey} x ${mKey}`
    ];

    const targetCandidates = [
      tKey,
      tName,
      tNode.id,
      tName.toUpperCase(),
      tKey.toUpperCase()
    ].filter(Boolean);

    let beta = null;
    let termUsed = `${mName} x ${sName}`;

    // 1. Check activeResults.paths or activeResults.structural?.paths
    const pathsList = activeResults.paths || activeResults.structural?.paths;
    if (Array.isArray(pathsList)) {
      for (const p of pathsList) {
        if (targetCandidates.some(t => t === p.to) && termCandidates.some(tc => tc.toLowerCase() === (p.from || '').toLowerCase())) {
          beta = Number(p.beta ?? p.original ?? p.path_coefficient);
          termUsed = p.from;
          break;
        }
      }
    }

    // 2. Check activeResults.structural?.path_coefficients[target][source]
    if (beta === null && activeResults.structural?.path_coefficients) {
      const paths = activeResults.structural.path_coefficients;
      for (const t of targetCandidates) {
        if (paths[t]) {
          for (const tc of termCandidates) {
            if (paths[t][tc] !== undefined) {
              beta = Number(paths[t][tc]);
              termUsed = tc;
              break;
            }
          }
          if (beta !== null) break;
          for (const srcKey of Object.keys(paths[t])) {
            if (termCandidates.some(tc => tc.toLowerCase() === srcKey.toLowerCase())) {
              beta = Number(paths[t][srcKey]);
              termUsed = srcKey;
              break;
            }
          }
          if (beta !== null) break;
        }
      }
    }

    if (beta === null) return null;

    // Look for bootstrap significance if available
    let tStat = null;
    let pVal = null;
    const bootPaths = activeResults.bootstrap?.path_coefficients ||
                      activeResults.significance?.path_coefficients ||
                      activeResults.bootstrap_significance?.path_coefficients;
    if (Array.isArray(bootPaths)) {
      for (const bp of bootPaths) {
        const pStr = bp.path || `${bp.from} -> ${bp.to}`;
        if (termCandidates.some(tc => pStr.toLowerCase().includes(tc.toLowerCase())) &&
            targetCandidates.some(t => pStr.toLowerCase().includes(t.toLowerCase()))) {
          tStat = bp.t_statistic ?? bp.t_stat ?? bp.t;
          pVal = bp.p_value ?? bp.p ?? bp.pval;
          break;
        }
      }
    }

    return {
      beta,
      term: termUsed,
      target: tName,
      t: tStat !== null && tStat !== undefined ? Number(tStat) : null,
      p: pVal !== null && pVal !== undefined ? Number(pVal) : null
    };
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

  function distToSegment(px, py, x1, y1, x2, y2) {
    const l2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
    if (l2 === 0) return Math.hypot(px - x1, py - y1);
    let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)));
  }

  function showConnectTooltip(x, y, text) {
    let tip = document.getElementById('canvas-connect-tooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'canvas-connect-tooltip';
      tip.style.position = 'fixed';
      tip.style.padding = '4px 8px';
      tip.style.borderRadius = '4px';
      tip.style.fontSize = '12px';
      tip.style.fontFamily = 'var(--font-sans, sans-serif)';
      tip.style.pointerEvents = 'none';
      tip.style.zIndex = '99999';
      tip.style.transition = 'opacity 0.1s ease';
      tip.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
      document.body.appendChild(tip);
    }
    tip.textContent = text;
    tip.style.background = '#ef4444';
    tip.style.color = '#ffffff';
    tip.style.left = `${x + 14}px`;
    tip.style.top = `${y + 14}px`;
    tip.style.display = 'block';
    tip.style.opacity = '1';
  }

  function hideConnectTooltip() {
    const tip = document.getElementById('canvas-connect-tooltip');
    if (tip) {
      tip.style.display = 'none';
      tip.style.opacity = '0';
    }
  }

  function wouldCreateCycle(sourceId, targetId, currentEdges) {
    if (sourceId === targetId) return true;
    const visited = new Set();
    const queue = [targetId];

    while (queue.length > 0) {
      const curr = queue.shift();
      if (curr === sourceId) return true;
      if (visited.has(curr)) continue;
      visited.add(curr);

      for (const edge of currentEdges) {
        if (edge.sourceId === curr) {
          const nextTarget = edge.targetId;
          const targetNode = nodes.find(n => n.id === nextTarget);
          if (targetNode && targetNode.isLatent !== false && !targetNode.isText) {
            if (!visited.has(nextTarget)) {
              queue.push(nextTarget);
            }
          }
        }
      }
    }
    return false;
  }

  function getEdgeMidpointAndPoints(sNode, tNode, edge) {
    const { x1, y1, x2, y2 } = getEdgeCoordinates(sNode, tNode, edge);
    let midX = (x1 + x2) / 2;
    let midY = (y1 + y2) / 2;
    let segments = [];

    if (edge.waypoints && edge.waypoints.length > 0) {
      const pts = [{ x: x1, y: y1 }, ...edge.waypoints, { x: x2, y: y2 }];
      for (let i = 0; i < pts.length - 1; i++) {
        segments.push([pts[i].x, pts[i].y, pts[i + 1].x, pts[i + 1].y]);
      }
      let totalLen = 0;
      const lens = [];
      for (let i = 0; i < pts.length - 1; i++) {
        const segLen = Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y);
        lens.push(segLen);
        totalLen += segLen;
      }
      const targetHalf = totalLen / 2;
      let acc = 0;
      for (let i = 0; i < lens.length; i++) {
        if (acc + lens[i] >= targetHalf) {
          const rem = targetHalf - acc;
          const ratio = lens[i] > 0 ? rem / lens[i] : 0;
          midX = pts[i].x + ratio * (pts[i + 1].x - pts[i].x);
          midY = pts[i].y + ratio * (pts[i + 1].y - pts[i].y);
          break;
        }
        acc += lens[i];
      }
    } else if (edge.curved) {
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const cx = mx + (-dy / len) * 40;
      const cy = my + (dx / len) * 40;

      const samplePts = [];
      const steps = 10;
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        const invT = 1 - t;
        const px = invT * invT * x1 + 2 * invT * t * cx + t * t * x2;
        const py = invT * invT * y1 + 2 * invT * t * cy + t * t * y2;
        samplePts.push({ x: px, y: py });
      }
      for (let i = 0; i < samplePts.length - 1; i++) {
        segments.push([samplePts[i].x, samplePts[i].y, samplePts[i + 1].x, samplePts[i + 1].y]);
      }
      midX = 0.25 * x1 + 0.5 * cx + 0.25 * x2;
      midY = 0.25 * y1 + 0.5 * cy + 0.25 * y2;
    } else {
      segments.push([x1, y1, x2, y2]);
      midX = (x1 + x2) / 2;
      midY = (y1 + y2) / 2;
    }

    return { midX, midY, segments };
  }

  function findPathTargetUnderPoint(svgPt) {
    let best = null;
    let minDistance = Infinity;

    for (const edge of edges) {
      const sNode = nodes.find(n => n.id === edge.sourceId);
      const tNode = nodes.find(n => n.id === edge.targetId);
      if (!sNode || !tNode) continue;
      // Must be structural path between latent constructs
      if (sNode.isLatent === false || tNode.isLatent === false || sNode.isText || tNode.isText) continue;

      const { midX, midY, segments } = getEdgeMidpointAndPoints(sNode, tNode, edge);

      // Check distance to any segment of this edge
      let distToEdge = Infinity;
      for (const [x1, y1, x2, y2] of segments) {
        const d = distToSegment(svgPt.x, svgPt.y, x1, y1, x2, y2);
        if (d < distToEdge) distToEdge = d;
      }

      const distToMid = Math.hypot(svgPt.x - midX, svgPt.y - midY);

      // Snap zone: within 16px of midpoint
      const inSnapZone = distToMid <= 16;
      // Near edge: within 12px of edge line
      const nearEdge = distToEdge <= 12;

      if (inSnapZone || nearEdge) {
        // Priority: snap zone gets strong preference (effective distance reduced by 50px)
        const effectiveDist = inSnapZone ? distToMid - 50 : distToEdge;
        if (effectiveDist < minDistance) {
          minDistance = effectiveDist;
          best = { edge, sNode, tNode, midX, midY, inSnapZone, distToEdge, distToMid };
        }
      }
    }
    return best;
  }

  function handleModerationOnEdge(edge) {
    if (!pendingModeratorNode) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Click a moderator construct first, then click a path.' } }));
      } catch (err) {}
      return false;
    }
    const sNode = nodes.find(n => n.id === edge.sourceId);
    const tNode = nodes.find(n => n.id === edge.targetId);
    if (!sNode || !tNode || sNode.isLatent === false || tNode.isLatent === false || sNode.isText || tNode.isText) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Moderation requires a structural path between latent constructs.' } }));
      } catch (err) {}
      return false;
    }
    if (pendingModeratorNode.id === sNode.id || pendingModeratorNode.id === tNode.id) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Moderator cannot be the predictor or outcome of the path.' } }));
      } catch (err) {}
      return false;
    }
    const exists = moderatingEffects.some(m => m.moderator === pendingModeratorNode.id && m.source === sNode.id && m.target === tNode.id);
    if (exists) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'This moderation effect already exists.' } }));
      } catch (err) {}
      return false;
    }
    if (wouldCreateCycle(pendingModeratorNode.id, tNode.id, edges)) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Cannot add moderation: would create a circular dependency.' } }));
      } catch (err) {}
      return false;
    }

    // Auto-add direct edge if not present
    if (!edges.some(e => e.sourceId === pendingModeratorNode.id && e.targetId === tNode.id)) {
      edges.push({
        id: generateId(),
        sourceId: pendingModeratorNode.id,
        targetId: tNode.id
      });
    }

    const newMod = {
      id: generateId(),
      moderator: pendingModeratorNode.id,
      source: sNode.id,
      target: tNode.id,
      method: 'two_stage',
      standardize: true
    };
    moderatingEffects.push(newMod);
    render();
    pushHistory();
    try {
      window.dispatchEvent(new CustomEvent('toast', { detail: { message: `Added moderation: ${pendingModeratorNode.label} on ${sNode.label} → ${tNode.label}` } }));
    } catch (err) {}
    return true;
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
        if (mode === 'moderation') {
          handleModerationOnEdge(edge);
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
        const isModerated = moderatingEffects.some(m => m.source === edge.sourceId && m.target === edge.targetId);
        let midX = (x1 + x2) / 2;
        let midY = (y1 + y2) / 2;

        if (isModerated) {
          // Fix 1c: Position at 35% from source along path so the landing dot at 50% does not cover it
          const t = 0.35;
          if (edge.waypoints && edge.waypoints.length > 0) {
            const pts = [{ x: x1, y: y1 }, ...edge.waypoints, { x: x2, y: y2 }];
            let totalLen = 0;
            const lens = [];
            for (let i = 0; i < pts.length - 1; i++) {
              const segLen = Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y);
              lens.push(segLen);
              totalLen += segLen;
            }
            const targetDist = totalLen * t;
            let acc = 0;
            for (let i = 0; i < lens.length; i++) {
              if (acc + lens[i] >= targetDist) {
                const rem = targetDist - acc;
                const ratio = lens[i] > 0 ? rem / lens[i] : 0;
                midX = pts[i].x + ratio * (pts[i + 1].x - pts[i].x);
                midY = pts[i].y + ratio * (pts[i + 1].y - pts[i].y);
                break;
              }
              acc += lens[i];
            }
          } else if (edge.curved) {
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.sqrt(dx * dx + dy * dy) || 1;
            const cx = mx + (-dy / len) * 40;
            const cy = my + (dx / len) * 40;
            const invT = 1 - t;
            midX = invT * invT * x1 + 2 * invT * t * cx + t * t * x2;
            midY = invT * invT * y1 + 2 * invT * t * cy + t * t * y2;
          } else {
            midX = x1 + t * (x2 - x1);
            midY = y1 + t * (y2 - y1);
          }
        } else {
          if (edge.waypoints && edge.waypoints.length > 0) {
            const numJoints = edge.waypoints.length;
            if (numJoints % 2 === 1) {
              const midIdx = Math.floor(numJoints / 2);
              midX = edge.waypoints[midIdx].x;
              midY = edge.waypoints[midIdx].y;
            } else {
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
        bg.setAttribute('fill', 'var(--canvas-badge-bg)');
        bg.style.fill = 'var(--canvas-badge-bg)';
        bg.setAttribute('stroke', selectedIds.has(edge.id) ? 'var(--color-accent)' : 'var(--canvas-badge-border)');
        bg.style.stroke = selectedIds.has(edge.id) ? 'var(--color-accent)' : 'var(--canvas-badge-border)';
        bg.setAttribute('stroke-width', '1');
        badgeG.appendChild(bg);

        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('dominant-baseline', 'central');
        txt.setAttribute('font-size', '10.5');
        txt.setAttribute('font-family', 'var(--font-mono, monospace)');
        txt.setAttribute('font-weight', '600');
        txt.setAttribute('fill', 'var(--canvas-badge-text)');
        txt.style.fill = 'var(--canvas-badge-text)';
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

    // Render Moderating Effects (SmartPLS 4 style dashed lines ending at midpoint of target path with dot)
    const pathModMap = new Map();
    moderatingEffects.forEach(mod => {
      const key = `${mod.source}->${mod.target}`;
      if (!pathModMap.has(key)) pathModMap.set(key, []);
      pathModMap.get(key).push(mod);
    });

    moderatingEffects.forEach(mod => {
      const modNode = nodes.find(n => n.id === mod.moderator);
      const sNode = nodes.find(n => n.id === mod.source);
      const tNode = nodes.find(n => n.id === mod.target);
      const targetEdge = edges.find(e => e.sourceId === mod.source && e.targetId === mod.target);
      if (!modNode || !sNode || !tNode || !targetEdge) return;

      const { x1, y1, x2, y2 } = getEdgeCoordinates(sNode, tNode, targetEdge);
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux = dx / len;
      const uy = dy / len;

      let mx = (x1 + x2) / 2;
      let my = (y1 + y2) / 2;

      // If multiple moderations on the same path, offset landing points along path segment by 16px steps
      const modsOnPath = pathModMap.get(`${mod.source}->${mod.target}`) || [mod];
      const modIndex = modsOnPath.findIndex(m => m.id === mod.id);
      const totalMods = modsOnPath.length;
      if (totalMods > 1) {
        const offset = (modIndex - (totalMods - 1) / 2) * 16;
        mx += offset * ux;
        my += offset * uy;
      }

      // Compute starting point on moderator construct boundary towards landing point (mx, my)
      const mdx = mx - modNode.x;
      const mdy = my - modNode.y;
      const mlen = Math.sqrt(mdx * mdx + mdy * mdy) || 1;
      const modR = (modNode.width ? modNode.width / 2 : NODE_R);
      const startX = modNode.x + (mdx / mlen) * modR;
      const startY = modNode.y + (mdy / mlen) * modR;

      const isSelected = selectedIds.has(mod.id);

      // 1. Dashed line from moderator to midpoint
      const dashLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      dashLine.setAttribute('d', `M ${startX} ${startY} L ${mx} ${my}`);
      dashLine.setAttribute('class', isSelected ? 'moderation-line selected' : 'moderation-line');
      dashLine.style.stroke = isSelected ? 'var(--color-accent, #6B4EE6)' : 'rgba(107, 78, 230, 0.75)';
      dashLine.style.strokeWidth = isSelected ? '2.5' : '1.5';
      dashLine.style.strokeDasharray = '4 4';
      dashLine.style.fill = 'none';
      dashLine.style.cursor = 'pointer';
      dashLine.setAttribute('marker-end', isSelected ? 'url(#arrow-open-selected)' : 'url(#arrow-open)');
      edgesLayer.appendChild(dashLine);

      // 2. Midpoint Dot (small circle where dashed line lands on the path)
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('cx', mx);
      dot.setAttribute('cy', my);
      dot.setAttribute('r', isSelected ? '5' : '4');
      dot.setAttribute('fill', isSelected ? 'var(--color-accent, #6B4EE6)' : '#6B4EE6');
      dot.setAttribute('stroke', '#ffffff');
      dot.setAttribute('stroke-width', '1.5');
      dot.style.cursor = 'pointer';
      edgesLayer.appendChild(dot);

      // 3. Invisible wide clickable hit-target for moderation line and dot
      const hitPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      hitPath.setAttribute('d', `M ${startX} ${startY} L ${mx} ${my}`);
      hitPath.style.stroke = 'rgba(0,0,0,0.001)';
      hitPath.style.strokeWidth = '16';
      hitPath.style.fill = 'none';
      hitPath.style.cursor = 'pointer';

      const handleModClick = (e) => {
        e.stopPropagation();
        if (mode === 'erase') {
          selectedIds.clear();
          selectedIds.add(mod.id);
          deleteSelected();
          return;
        }
        if (mode === 'select') {
          if (!e.shiftKey) clearSelection();
          selectedIds.add(mod.id);
          render();
          try {
            window.dispatchEvent(new CustomEvent('selectionChange', {
              detail: { type: 'moderation', moderation: mod }
            }));
            window.dispatchEvent(new CustomEvent('moderation-selected', {
              detail: { moderation: mod }
            }));
          } catch (err) {}
        }
      };

      hitPath.addEventListener('click', handleModClick);
      dot.addEventListener('click', handleModClick);
      edgesLayer.appendChild(hitPath);

      // 4. Moderation path coefficient badge (Fix 1c)
      const modDetails = getModerationDetails(mod);
      if (modDetails && modDetails.beta !== null && modDetails.beta !== undefined) {
        const badgeX = (startX + mx) / 2;
        const badgeY = (startY + my) / 2;

        const badgeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        badgeG.setAttribute('class', 'edge-result-badge moderation-badge');
        badgeG.setAttribute('transform', `translate(${badgeX}, ${badgeY})`);
        badgeG.setAttribute('pointer-events', 'auto');
        badgeG.style.cursor = 'pointer';

        const textVal = modDetails.beta.toFixed(3);
        const pillW = Math.max(34, textVal.length * 7.5 + 10);
        const pillH = 18;

        const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bg.setAttribute('x', -pillW / 2);
        bg.setAttribute('y', -pillH / 2);
        bg.setAttribute('width', pillW);
        bg.setAttribute('height', pillH);
        bg.setAttribute('rx', '4');
        bg.setAttribute('fill', 'var(--canvas-badge-bg)');
        bg.style.fill = 'var(--canvas-badge-bg)';
        bg.setAttribute('stroke', isSelected ? 'var(--color-accent)' : 'rgba(107, 78, 230, 0.7)');
        bg.style.stroke = isSelected ? 'var(--color-accent)' : 'rgba(107, 78, 230, 0.7)';
        bg.setAttribute('stroke-width', isSelected ? '1.5' : '1');
        badgeG.appendChild(bg);

        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('dominant-baseline', 'central');
        txt.setAttribute('font-size', '10.5');
        txt.setAttribute('font-family', 'var(--font-mono, monospace)');
        txt.setAttribute('font-weight', '600');
        txt.setAttribute('fill', 'var(--canvas-badge-text)');
        txt.style.fill = 'var(--canvas-badge-text)';
        txt.textContent = textVal;
        badgeG.appendChild(txt);

        let tooltipText = `${modDetails.term} → ${modDetails.target}: β = ${modDetails.beta.toFixed(3)}`;
        if (modDetails.t !== null) tooltipText += `, t = ${modDetails.t.toFixed(3)}`;
        if (modDetails.p !== null) tooltipText += `, p = ${modDetails.p.toFixed(3)}`;

        const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        titleEl.textContent = tooltipText;
        badgeG.appendChild(titleEl);

        const lineTitle = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        lineTitle.textContent = tooltipText;
        hitPath.appendChild(lineTitle);

        badgeG.addEventListener('click', handleModClick);
        edgesLayer.appendChild(badgeG);
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
        g.appendChild(createNodeShape(node, NODE_R * 2, NODE_R * 2, 'var(--canvas-latent-fill)', 'var(--canvas-latent-stroke)', isSelected));

        // Visual indicator for pending moderator construct
        if (pendingModeratorNode && pendingModeratorNode.id === node.id) {
          const modRing = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          modRing.setAttribute('r', (NODE_R + 6));
          modRing.setAttribute('fill', 'none');
          modRing.setAttribute('stroke', 'var(--color-accent, #6B4EE6)');
          modRing.setAttribute('stroke-width', '2.5');
          modRing.setAttribute('stroke-dasharray', '4 4');
          g.appendChild(modRing);
        }
        
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
          text.setAttribute('fill', node.color || 'var(--canvas-latent-text)');
          text.style.fill = node.color || 'var(--canvas-latent-text)';
        } else {
          text.setAttribute('y', h/2 + 24);
          text.setAttribute('fill', node.color || 'var(--color-text-primary)');
          text.style.fill = node.color || 'var(--color-text-primary)';
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
            r2Text.setAttribute('fill', 'var(--canvas-latent-text)');
            r2Text.style.fill = 'var(--canvas-latent-text)';
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
            r2Label.setAttribute('fill', 'var(--canvas-latent-text)');
            r2Label.style.fill = 'var(--canvas-latent-text)';
            r2Label.style.opacity = '0.85';
            r2Label.textContent = 'R²';
            r2Group.appendChild(r2Label);

            const r2Text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            r2Text.setAttribute('text-anchor', 'middle');
            r2Text.setAttribute('dominant-baseline', 'central');
            r2Text.setAttribute('y', 8);
            r2Text.setAttribute('font-size', '12.5');
            r2Text.setAttribute('font-weight', '600');
            r2Text.setAttribute('font-family', 'var(--font-mono, monospace)');
            r2Text.setAttribute('fill', 'var(--canvas-latent-text)');
            r2Text.style.fill = 'var(--canvas-latent-text)';
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
        
        const defaultFill = node.isMissingInDataset ? 'var(--canvas-missing-fill, #fef2f2)' : 'var(--canvas-manifest-fill)';
        const defaultStroke = node.isMissingInDataset ? '#ef4444' : 'var(--canvas-manifest-stroke)';
        g.appendChild(createNodeShape(node, indWidth, indHeight, defaultFill, defaultStroke, isSelected));

        if (isSelected) {
          const gap = 8;
          const selShape = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          selShape.setAttribute('x', -(w/2 + gap));
          selShape.setAttribute('y', -(h/2 + gap));
          selShape.setAttribute('width', w + gap*2);
          selShape.setAttribute('height', h + gap*2);
          selShape.setAttribute('rx', '4');
          selShape.setAttribute('fill', 'none');
          selShape.setAttribute('stroke', node.isMissingInDataset ? '#ef4444' : 'var(--color-accent, #6B4EE6)');
          selShape.setAttribute('stroke-width', '2');
          selShape.setAttribute('stroke-dasharray', '6 6');
          g.appendChild(selShape);
          
          // Resize handle
          const handle = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          handle.setAttribute('x', w/2 + gap - 4);
          handle.setAttribute('y', h/2 + gap - 4);
          handle.setAttribute('width', '8');
          handle.setAttribute('height', '8');
          handle.setAttribute('fill', node.isMissingInDataset ? '#ef4444' : 'var(--color-accent, #6B4EE6)');
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
        indText.setAttribute('fill', node.isMissingInDataset ? '#ef4444' : (node.color || 'var(--canvas-manifest-text)'));
        indText.setAttribute('font-size', node.fontSize || '10');
        if (node.bold) indText.setAttribute('font-weight', 'bold');
        if (node.italic) indText.setAttribute('font-style', 'italic');
        if (node.underline) indText.setAttribute('text-decoration', 'underline');
        indText.setAttribute('font-family', node.fontFamily || 'var(--font-mono)');
        g.appendChild(indText);

        if (node.isMissingInDataset) {
          const warnBadge = document.createElementNS('http://www.w3.org/2000/svg', 'g');
          warnBadge.setAttribute('transform', `translate(${w/2 - 4}, ${-h/2 + 4})`);
          warnBadge.style.cursor = 'help';
          
          const warnCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          warnCircle.setAttribute('r', '6');
          warnCircle.setAttribute('fill', '#ef4444');
          warnCircle.setAttribute('stroke', '#ffffff');
          warnCircle.setAttribute('stroke-width', '1.2');
          
          const warnText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          warnText.textContent = '!';
          warnText.setAttribute('text-anchor', 'middle');
          warnText.setAttribute('dominant-baseline', 'central');
          warnText.setAttribute('fill', '#ffffff');
          warnText.setAttribute('font-size', '9');
          warnText.setAttribute('font-weight', 'bold');
          
          const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
          titleEl.textContent = node.datasetError || `Column "${node.label}" not found in current dataset`;
          warnBadge.appendChild(titleEl);

          warnBadge.appendChild(warnCircle);
          warnBadge.appendChild(warnText);
          g.appendChild(warnBadge);
        }
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
            path.setAttribute('stroke', 'var(--canvas-edge-stroke)');
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
              bg.setAttribute('fill', 'var(--canvas-badge-bg)');
              bg.setAttribute('stroke', 'var(--canvas-badge-border)');
              bg.setAttribute('stroke-width', '0.75');
              badgeG.appendChild(bg);

              const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
              txt.setAttribute('text-anchor', 'middle');
              txt.setAttribute('dominant-baseline', 'central');
              txt.setAttribute('font-size', '9.5');
              txt.setAttribute('font-family', 'var(--font-mono, monospace)');
              txt.setAttribute('font-weight', '500');
              txt.setAttribute('fill', 'var(--canvas-badge-text)');
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

    // Only LEFT-click (e.button === 0) initiates dragging or canvas operations
    if (e.button !== 0) {
      if (e.button === 2) {
        // Right-click: ensure target node is selected for context actions, but NEVER drag!
        if (!e.shiftKey && !selectedIds.has(node.id)) {
          clearSelection();
        }
        selectedIds.add(node.id);
        render();
      }
      return;
    }
    
    e.preventDefault();
    
    if (mode === 'erase') {
      selectedIds.clear();
      selectedIds.add(node.id);
      deleteSelected();
      return;
    }

    if (mode === 'moderation') {
      if (node.isLatent !== false && !node.isText) {
        pendingModeratorNode = node;
        render();
        try {
          window.dispatchEvent(new CustomEvent('toast', { detail: { message: `Moderator "${node.label}" selected. Now click an existing structural path.` } }));
        } catch (err) {}
      }
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
    // If context menu is open, completely freeze any node movement!
    if (contextMenu && contextMenu.style.display === 'block') {
      draggingNode = null;
      isMarquee = false;
      return;
    }

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
      
      const dx = newX - draggingNode.x;
      const dy = newY - draggingNode.y;
      if (dx !== 0 || dy !== 0) {
        const nodesToMove = new Set(selectedIds);
        nodes.forEach(n => {
          if (n.parentId && nodesToMove.has(n.parentId)) {
            nodesToMove.add(n.id);
          }
        });
        nodes.forEach(n => {
          if (nodesToMove.has(n.id)) {
            n.x += dx;
            n.y += dy;
          }
        });
      }
      render();
    }
    
    if (tempConnecting && mode === 'connect') {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      // Resolution order: (1) construct under cursor wins
      const targetNode = nodes.find(n => {
        if (n.id === connectStartNode.id) return false;
        const dx = n.x - svgPt.x;
        const dy = n.y - svgPt.y;
        return Math.sqrt(dx*dx + dy*dy) <= Math.max(NODE_R, (n.width ? n.width/2 : 40));
      });

      if (targetNode) {
        guidesLayer.innerHTML = '';
        hideConnectTooltip();
        svg.style.cursor = 'crosshair';
        tempLine.setAttribute('x2', targetNode.x);
        tempLine.setAttribute('y2', targetNode.y);
        tempLine.setAttribute('stroke-dasharray', '');
        tempLine.setAttribute('stroke-width', '2');

        const isIllegal = targetNode.isText === true || connectStartNode.isText === true || edges.some(edge => 
          (edge.sourceId === connectStartNode.id && edge.targetId === targetNode.id) ||
          (edge.sourceId === targetNode.id && edge.targetId === connectStartNode.id)
        );
        if (isIllegal) {
          tempLine.setAttribute('stroke', '#ef4444');
        } else {
          tempLine.setAttribute('stroke', 'var(--color-accent, #6B4EE6)');
        }
      } else if (connectStartNode.isLatent !== false && !connectStartNode.isText) {
        // (2) Path under cursor -> moderation preview
        const pathTarget = findPathTargetUnderPoint(svgPt);
        if (pathTarget) {
          const { edge, sNode, tNode, midX, midY } = pathTarget;
          const modId = connectStartNode.id;

          let invalidReason = null;
          if (modId === sNode.id || modId === tNode.id) {
            invalidReason = 'Moderator cannot be predictor or outcome of the path';
          } else if (moderatingEffects.some(m => m.moderator === modId && m.source === sNode.id && m.target === tNode.id)) {
            invalidReason = 'This moderation effect already exists';
          } else if (wouldCreateCycle(modId, tNode.id, edges)) {
            invalidReason = 'Cannot add moderation: would create a circular dependency';
          }

          if (invalidReason) {
            guidesLayer.innerHTML = '';
            tempLine.setAttribute('x2', svgPt.x);
            tempLine.setAttribute('y2', svgPt.y);
            tempLine.setAttribute('stroke', '#ef4444');
            tempLine.setAttribute('stroke-dasharray', '4 4');
            tempLine.setAttribute('stroke-width', '2');
            svg.style.cursor = 'not-allowed';
            showConnectTooltip(e.clientX, e.clientY, invalidReason);
          } else {
            // Valid path: snap preview to midpoint, accent dashed line, midpoint handle, copy cursor
            hideConnectTooltip();
            tempLine.setAttribute('x2', midX);
            tempLine.setAttribute('y2', midY);
            tempLine.setAttribute('stroke', 'var(--color-accent, #6B4EE6)');
            tempLine.setAttribute('stroke-dasharray', '4 4');
            tempLine.setAttribute('stroke-width', '2.5');
            svg.style.cursor = 'copy';

            guidesLayer.innerHTML = '';
            const snapCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            snapCircle.setAttribute('cx', midX);
            snapCircle.setAttribute('cy', midY);
            snapCircle.setAttribute('r', '6');
            snapCircle.setAttribute('fill', 'var(--color-accent, #6B4EE6)');
            snapCircle.setAttribute('stroke', '#ffffff');
            snapCircle.setAttribute('stroke-width', '2');
            snapCircle.style.pointerEvents = 'none';
            guidesLayer.appendChild(snapCircle);
          }
        } else {
          guidesLayer.innerHTML = '';
          hideConnectTooltip();
          tempLine.setAttribute('x2', svgPt.x);
          tempLine.setAttribute('y2', svgPt.y);
          tempLine.setAttribute('stroke', 'var(--color-text-primary)');
          tempLine.setAttribute('stroke-dasharray', '5 5');
          tempLine.setAttribute('stroke-width', '2');
          svg.style.cursor = 'crosshair';
        }
      } else {
        guidesLayer.innerHTML = '';
        hideConnectTooltip();
        tempLine.setAttribute('x2', svgPt.x);
        tempLine.setAttribute('y2', svgPt.y);
        tempLine.setAttribute('stroke', 'var(--color-text-primary)');
        tempLine.setAttribute('stroke-dasharray', '5 5');
        tempLine.setAttribute('stroke-width', '2');
        svg.style.cursor = 'crosshair';
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
      window.dispatchEvent(new CustomEvent('canvas-changed'));
    }
    
    if (tempConnecting) {
      guidesLayer.innerHTML = '';
      hideConnectTooltip();
      svg.style.cursor = '';

      // Find what we dropped on
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const svgPt = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      
      // Resolution order: (1) construct under cursor wins
      const targetNode = nodes.find(n => {
        if (n.id === connectStartNode.id) return false;
        const dx = n.x - svgPt.x;
        const dy = n.y - svgPt.y;
        return Math.sqrt(dx*dx + dy*dy) <= Math.max(NODE_R, (n.width ? n.width/2 : 40));
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
      } else if (connectStartNode.isLatent !== false && !connectStartNode.isText) {
        // (2) Drop on existing path line -> moderation!
        const pathTarget = findPathTargetUnderPoint(svgPt);
        if (pathTarget) {
          const { edge, sNode, tNode } = pathTarget;
          const modId = connectStartNode.id;

          if (modId === sNode.id || modId === tNode.id) {
            try {
              window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Moderator cannot be the predictor or outcome of the path.' } }));
            } catch (err) {}
          } else if (moderatingEffects.some(m => m.moderator === modId && m.source === sNode.id && m.target === tNode.id)) {
            try {
              window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'This moderation effect already exists.' } }));
            } catch (err) {}
          } else if (wouldCreateCycle(modId, tNode.id, edges)) {
            try {
              window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Cannot add moderation: would create a circular dependency (feedback loop).' } }));
            } catch (err) {}
          } else {
            // Valid moderation!
            // 1. Auto-add direct edge from moderator to outcome if it does not exist
            if (!edges.some(e => e.sourceId === modId && e.targetId === tNode.id)) {
              edges.push({
                id: generateId(),
                sourceId: modId,
                targetId: tNode.id
              });
            }

            // 2. Add moderating effect
            const newMod = {
              id: generateId(),
              moderator: modId,
              source: sNode.id,
              target: tNode.id,
              method: 'two_stage',
              standardize: true
            };
            moderatingEffects.push(newMod);

            // Single undoable action
            render();
            pushHistory();

            try {
              window.dispatchEvent(new CustomEvent('toast', { detail: { message: `Added moderation: ${connectStartNode.label} on ${sNode.label} → ${tNode.label}` } }));
            } catch (err) {}
          }
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
    try {
      window.dispatchEvent(new CustomEvent('selectionChange', { detail: { type: null } }));
      window.dispatchEvent(new CustomEvent('moderation-selected', { detail: { moderation: null } }));
    } catch (err) {}
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
    draggingNode = null;
    isMarquee = false;
  }
  
  contextMenu.innerHTML = `
    <div class="ctx-item" id="ctx-copy" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
      <span class="material-symbols-outlined" style="font-size: 16px;">content_copy</span> Copy
    </div>
    <div class="ctx-item" id="ctx-paste" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
      <span class="material-symbols-outlined" style="font-size: 16px;">content_paste</span> Paste
    </div>
    <div class="ctx-item" id="ctx-duplicate" style="padding: 6px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px;">
      <span class="material-symbols-outlined" style="font-size: 16px;">control_point_duplicate</span> Duplicate
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

  contextMenu.querySelector('#ctx-copy')?.addEventListener('click', () => {
    if (ctxTargetId && !selectedIds.has(ctxTargetId)) {
      selectedIds.clear();
      selectedIds.add(ctxTargetId);
    }
    copySelected();
    hideContextMenu();
  });

  contextMenu.querySelector('#ctx-paste')?.addEventListener('click', () => {
    pasteClipboard();
    hideContextMenu();
  });

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
        const copy = JSON.parse(JSON.stringify(node));
        copy.id = generateId();
        copy.x = (node.x || 0) + 40;
        copy.y = (node.y || 0) + 40;
        if (copy.label) {
          copy.label = `${copy.label}_copy`;
        }
        nodes.push(copy);
        render();
        pushHistory();
        window.dispatchEvent(new CustomEvent('canvas-changed'));
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

  let contextMenuMousePos = null;

  function showContextMenu(e, id) {
    e.preventDefault();
    e.stopPropagation();
    draggingNode = null;
    isMarquee = false;
    ctxTargetId = id;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    contextMenuMousePos = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
    
    // Select the item
    if (!e.shiftKey && !selectedIds.has(id)) {
      clearSelection();
    }
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
    
    const ctxCopy = contextMenu.querySelector('#ctx-copy');
    const ctxPaste = contextMenu.querySelector('#ctx-paste');
    if (ctxCopy) ctxCopy.style.display = 'flex';
    if (ctxPaste) ctxPaste.style.display = 'flex';

    // Position menu
    let x = e.clientX;
    let y = e.clientY;
    if (x + 120 > window.innerWidth) x -= 120;
    if (y + 100 > window.innerHeight) y -= 100;
    contextMenu.style.left = `${x}px`;
    contextMenu.style.top = `${y}px`;
  }

  svg.addEventListener('contextmenu', (e) => {
    draggingNode = null;
    isMarquee = false;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    contextMenuMousePos = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());

    if (e.target === svg || e.target === bgRect) {
      e.preventDefault();
      ctxTargetId = null;
      contextMenu.style.display = 'block';
      const ctxCopy = contextMenu.querySelector('#ctx-copy');
      const ctxPaste = contextMenu.querySelector('#ctx-paste');
      const ctxDuplicate = contextMenu.querySelector('#ctx-duplicate');
      const ctxRename = contextMenu.querySelector('#ctx-rename');
      const ctxToggleMode = contextMenu.querySelector('#ctx-toggle-mode');
      const ctxDelete = contextMenu.querySelector('#ctx-delete');

      if (ctxCopy) ctxCopy.style.display = selectedIds.size > 0 ? 'flex' : 'none';
      if (ctxPaste) ctxPaste.style.display = 'flex';
      if (ctxDuplicate) ctxDuplicate.style.display = 'none';
      if (ctxRename) ctxRename.style.display = 'none';
      if (ctxToggleMode) ctxToggleMode.style.display = 'none';
      if (ctxDelete) ctxDelete.style.display = selectedIds.size > 0 ? 'flex' : 'none';

      let x = e.clientX;
      let y = e.clientY;
      if (x + 120 > window.innerWidth) x -= 120;
      if (y + 100 > window.innerHeight) y -= 100;
      contextMenu.style.left = `${x}px`;
      contextMenu.style.top = `${y}px`;
    }
  });

  function copySelected() {
    if (selectedIds.size === 0) return;
    
    // Find all selected latent and text nodes
    const selectedNodes = nodes.filter(n => selectedIds.has(n.id));
    
    // Automatically include child indicators of copied latent constructs
    const latentIds = new Set(selectedNodes.filter(n => n.isLatent).map(n => n.id));
    const childIndicators = nodes.filter(n => n.parentId && latentIds.has(n.parentId));
    
    const allNodesToCopy = [...selectedNodes];
    childIndicators.forEach(ind => {
      if (!allNodesToCopy.some(n => n.id === ind.id)) {
        allNodesToCopy.push(ind);
      }
    });

    const copiedNodeIds = new Set(allNodesToCopy.map(n => n.id));

    // Copy edges between any of these nodes
    const copiedEdges = edges.filter(e => copiedNodeIds.has(e.sourceId) && copiedNodeIds.has(e.targetId));

    const payload = {
      version: '1.0',
      timestamp: Date.now(),
      nodes: JSON.parse(JSON.stringify(allNodesToCopy)),
      edges: JSON.parse(JSON.stringify(copiedEdges)),
      datasetColumns: window.__activeDatasetColumns || []
    };

    window.__statsem_clipboard = payload;
    try {
      localStorage.setItem('statsem_model_clipboard', JSON.stringify(payload));
    } catch (e) {}

    console.log(`[Canvas] Copied ${allNodesToCopy.length} nodes and ${copiedEdges.length} edges.`);
  }

  function pasteClipboard() {
    let payload = window.__statsem_clipboard;
    if (!payload) {
      try {
        const stored = localStorage.getItem('statsem_model_clipboard');
        if (stored) payload = JSON.parse(stored);
      } catch (e) {}
    }

    if (!payload || !payload.nodes || payload.nodes.length === 0) return;

    // Determine current active dataset columns
    const currentDatasetCols = (window.__activeDatasetColumns || []).map(c => String(c).trim().toLowerCase());
    const hasDataset = currentDatasetCols.length > 0;

    // Calculate bounding box of copied elements
    let copiedMinX = Infinity, copiedMaxX = -Infinity;
    let copiedMinY = Infinity, copiedMaxY = -Infinity;
    payload.nodes.forEach(n => {
      copiedMinX = Math.min(copiedMinX, n.x);
      copiedMaxX = Math.max(copiedMaxX, n.x);
      copiedMinY = Math.min(copiedMinY, n.y);
      copiedMaxY = Math.max(copiedMaxY, n.y);
    });
    const copiedCenterX = (copiedMinX + copiedMaxX) / 2;
    const copiedCenterY = (copiedMinY + copiedMaxY) / 2;

    const isSameModel = payload.nodes.some(pn => nodes.some(n => n.id === pn.id));

    let shiftX = 0;
    let shiftY = 0;

    if (contextMenuMousePos) {
      // User right-clicked on canvas to paste -> place center at right-click location!
      shiftX = contextMenuMousePos.x - copiedCenterX;
      shiftY = contextMenuMousePos.y - copiedCenterY;
      contextMenuMousePos = null;
    } else if (isSameModel) {
      // Pasting within the same model -> offset slightly
      shiftX = 40;
      shiftY = 40;
    } else if (nodes.length > 0) {
      // Cross-model paste into a canvas that has an existing model:
      // Find bounding box of the existing model
      let existMinX = Infinity, existMaxX = -Infinity;
      let existMinY = Infinity, existMaxY = -Infinity;
      nodes.forEach(n => {
        existMinX = Math.min(existMinX, n.x);
        existMaxX = Math.max(existMaxX, n.x);
        existMinY = Math.min(existMinY, n.y);
        existMaxY = Math.max(existMaxY, n.y);
      });

      // Place neatly to the right of the existing model (with 80px gap), top-aligned
      shiftX = (existMaxX + 80) - copiedMinX;
      shiftY = existMinY - copiedMinY;
    } else {
      // Target model is empty -> center in the visible viewport!
      const rect = svg.getBoundingClientRect();
      const pt = svg.createSVGPoint();
      pt.x = rect.left + rect.width / 2;
      pt.y = rect.top + rect.height / 2;
      const viewCenter = pt.matrixTransform(zoomLayer.getScreenCTM().inverse());
      shiftX = viewCenter.x - copiedCenterX;
      shiftY = viewCenter.y - copiedCenterY;
    }

    const idMap = new Map();

    // Generate new unique IDs
    payload.nodes.forEach(n => {
      idMap.set(n.id, generateId());
    });

    const newNodes = [];
    let hasMissingVariables = false;

    payload.nodes.forEach(oldNode => {
      const newNode = JSON.parse(JSON.stringify(oldNode));
      newNode.id = idMap.get(oldNode.id);
      if (oldNode.parentId && idMap.has(oldNode.parentId)) {
        newNode.parentId = idMap.get(oldNode.parentId);
      }
      newNode.x = (oldNode.x || 0) + shiftX;
      newNode.y = (oldNode.y || 0) + shiftY;

      // Dataset compatibility check:
      // If indicator, check if its label exists in current dataset!
      if (!newNode.isLatent && !newNode.isText) {
        const colName = String(newNode.label || '').trim().toLowerCase();
        if (hasDataset && !currentDatasetCols.includes(colName)) {
          newNode.isMissingInDataset = true;
          newNode.datasetError = `Column "${newNode.label}" is missing from active dataset`;
          newNode.stroke = '#ef4444';
          newNode.fill = '#fef2f2';
          hasMissingVariables = true;
        } else {
          newNode.isMissingInDataset = false;
        }
      }

      newNodes.push(newNode);
    });

    const newEdges = [];
    payload.edges.forEach(oldEdge => {
      const newSource = idMap.get(oldEdge.sourceId);
      const newTarget = idMap.get(oldEdge.targetId);
      if (newSource && newTarget) {
        const newEdge = JSON.parse(JSON.stringify(oldEdge));
        newEdge.id = generateId();
        newEdge.sourceId = newSource;
        newEdge.targetId = newTarget;
        if (newEdge.waypoints) {
          newEdge.waypoints.forEach(wp => {
            wp.x += shiftX;
            wp.y += shiftY;
          });
        }
        newEdges.push(newEdge);
      }
    });

    // Add to canvas
    nodes.push(...newNodes);
    edges.push(...newEdges);

    // Select the pasted elements
    selectedIds.clear();
    newNodes.forEach(n => selectedIds.add(n.id));

    if (emptyHint) {
      emptyHint.style.display = nodes.length === 0 ? 'block' : 'none';
    }

    render();
    pushHistory();
    window.dispatchEvent(new CustomEvent('canvas-changed'));

    if (hasMissingVariables) {
      console.warn('[Canvas] Pasted elements contain indicators not in active dataset (marked in red).');
    }
  }

  function validateDatasetVariables() {
    const currentDatasetCols = (window.__activeDatasetColumns || []).map(c => String(c).trim().toLowerCase());
    if (currentDatasetCols.length === 0) return;
    nodes.forEach(n => {
      if (n.isLatent === false && !n.isText) {
        const colName = String(n.label || '').trim().toLowerCase();
        if (!currentDatasetCols.includes(colName)) {
          n.isMissingInDataset = true;
          n.datasetError = `Column "${n.label}" is missing from active dataset`;
        } else {
          n.isMissingInDataset = false;
          n.datasetError = null;
        }
      }
    });
  }

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

    // Handle moderating effects deletion & cascade deletion
    const initialModCount = moderatingEffects.length;
    let explicitModDeleted = false;
    let cascadeModDeleted = false;

    moderatingEffects = moderatingEffects.filter(m => {
      if (selectedIds.has(m.id)) {
        explicitModDeleted = true;
        return false;
      }
      if (nodesToDelete.has(m.moderator) || nodesToDelete.has(m.source) || nodesToDelete.has(m.target)) {
        cascadeModDeleted = true;
        return false;
      }
      const pathEdgeStillExists = edges.some(e => e.sourceId === m.source && e.targetId === m.target);
      if (!pathEdgeStillExists) {
        cascadeModDeleted = true;
        return false;
      }
      return true;
    });

    if (cascadeModDeleted) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Moderation effect removed (cascade)' } }));
      } catch (e) {}
    } else if (explicitModDeleted) {
      try {
        window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Moderation effect deleted' } }));
      } catch (e) {}
    }

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

    if (e.key === 'Escape') {
      pendingModeratorNode = null;
      setMode('select');
      updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Select"]'));
      render();
      return;
    }

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
      } else if (e.key.toLowerCase() === 'm') {
        setMode('connect');
        updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Path Connector"]'));
        try {
          window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'Connect mode active: Drag from a construct to the middle of a path to add moderation.' } }));
        } catch (err) {}
      } else if (e.key.toLowerCase() === 'e') {
        setMode('erase');
        updateToolbarUI(document.querySelector('.canvas-toolbar .tb-btn[title*="Erase"]'));
      }
    }

    // Classic Undo & Redo shortcuts
    if (e.metaKey || e.ctrlKey) {
      if (e.key.toLowerCase() === 'c') {
        e.preventDefault();
        e.stopPropagation();
        copySelected();
        return;
      }
      if (e.key.toLowerCase() === 'v') {
        e.preventDefault();
        e.stopPropagation();
        pasteClipboard();
        return;
      }
      if (e.key.toLowerCase() === 'a') {
        e.preventDefault();
        e.stopPropagation();
        selectedIds.clear();
        nodes.forEach(n => selectedIds.add(n.id));
        render();
        return;
      }
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

    const moderating_effects = moderatingEffects.map(m => ({
      id: m.id,
      moderator: m.moderator,
      source: m.source,
      target: m.target,
      method: m.method || 'two_stage',
      standardize: m.standardize !== false
    }));

    return {
      constructs,
      indicators,
      paths,
      moderating_effects
    };
  }

  function getModelCanvasState() {
    return {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
      moderatingEffects: JSON.parse(JSON.stringify(moderatingEffects)),
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
    if (state.moderatingEffects && Array.isArray(state.moderatingEffects)) {
      moderatingEffects = JSON.parse(JSON.stringify(state.moderatingEffects));
    } else if (state.moderating_effects && Array.isArray(state.moderating_effects)) {
      moderatingEffects = JSON.parse(JSON.stringify(state.moderating_effects));
    } else {
      moderatingEffects = [];
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

  function getModeratingEffects() {
    return JSON.parse(JSON.stringify(moderatingEffects));
  }
  function setModeratingEffects(list) {
    moderatingEffects = JSON.parse(JSON.stringify(list || []));
    render();
    pushHistory();
  }
  function updateModeratingEffect(id, patch) {
    const mod = moderatingEffects.find(m => m.id === id);
    if (mod) {
      Object.assign(mod, patch);
      render();
      pushHistory();
    }
  }
  function deleteModeratingEffect(id) {
    moderatingEffects = moderatingEffects.filter(m => m.id !== id);
    selectedIds.delete(id);
    render();
    pushHistory();
  }
  function getSelectedModeratingEffect() {
    for (const id of selectedIds) {
      const mod = moderatingEffects.find(m => m.id === id);
      if (mod) return JSON.parse(JSON.stringify(mod));
    }
    return null;
  }

  window.getModeratingEffects = getModeratingEffects;
  window.setModeratingEffects = setModeratingEffects;
  window.updateModeratingEffect = updateModeratingEffect;
  window.deleteModeratingEffect = deleteModeratingEffect;
  window.getSelectedModeratingEffect = getSelectedModeratingEffect;
  window.exportModelSpec = exportModelSpec;
  window.getModelCanvasState = getModelCanvasState;
  window.loadModelCanvasState = loadModelCanvasState;
  window.toggleMeasurementMode = toggleMeasurementMode;
  window.deleteSelectedModelPart = deleteSelected;
  window.canvasUndo = undo;
  window.canvasRedo = redo;
  window.copySelected = copySelected;
  window.pasteClipboard = pasteClipboard;
  window.validateDatasetVariables = validateDatasetVariables;
  window.setCanvasResults = setCanvasResults;
  window.renderModelCanvas = render;
  window.clearModelCanvas = clearModelCanvas;
  window.resetModelStyles = resetModelStyles;

  try {
    if (typeof MutationObserver !== 'undefined' && typeof document !== 'undefined') {
      const themeObserver = new MutationObserver(() => {
        render();
      });
      themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme', 'data-dark-variant']
      });
    }
  } catch (e) {}
}

export function copySelected() {
  if (typeof window !== 'undefined' && window.copySelected) {
    window.copySelected();
  }
}

export function pasteClipboard() {
  if (typeof window !== 'undefined' && window.pasteClipboard) {
    window.pasteClipboard();
  }
}

export function setCanvasDatasetColumns(columns) {
  if (typeof window !== 'undefined') {
    window.__activeDatasetColumns = columns || [];
    if (window.validateDatasetVariables) {
      window.validateDatasetVariables();
      if (window.renderModelCanvas) window.renderModelCanvas();
    }
  }
}

export function resetModelStyles() {
  if (typeof window !== 'undefined' && window.resetModelStyles) {
    window.resetModelStyles();
  }
}

export function clearModelCanvas() {
  if (typeof window !== 'undefined' && window.clearModelCanvas) {
    window.clearModelCanvas();
  }
}

export function renderModelCanvas() {
  if (typeof window !== 'undefined' && window.renderModelCanvas) {
    window.renderModelCanvas();
  }
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

export function getModeratingEffects() {
  if (typeof window !== 'undefined' && window.getModeratingEffects) {
    return window.getModeratingEffects();
  }
  return [];
}

export function updateModeratingEffect(id, patch) {
  if (typeof window !== 'undefined' && window.updateModeratingEffect) {
    window.updateModeratingEffect(id, patch);
  }
}

export function deleteModeratingEffect(id) {
  if (typeof window !== 'undefined' && window.deleteModeratingEffect) {
    window.deleteModeratingEffect(id);
  }
}

export function getSelectedModeratingEffect() {
  if (typeof window !== 'undefined' && window.getSelectedModeratingEffect) {
    return window.getSelectedModeratingEffect();
  }
  return null;
}


