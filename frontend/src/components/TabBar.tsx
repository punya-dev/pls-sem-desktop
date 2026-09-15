import React, { useEffect, useRef, useState } from 'react';
import { useStore, type AppTab } from '../store';
import WorkspaceModal from './WorkspaceModal';

export const TabBar: React.FC = () => {
  const { tabs, activeTabId, setActiveTab, closeTab, openTab, workspaces } = useStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Close dropdown on outside click and reset search
  useEffect(() => {
    if (!isDropdownOpen) {
      setSearchQuery('');
      return;
    }
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    window.addEventListener('mousedown', handleOutsideClick);

    // Auto-focus search input when opened
    const timer = setTimeout(() => {
      searchInputRef.current?.focus();
    }, 40);

    return () => {
      window.removeEventListener('mousedown', handleOutsideClick);
      clearTimeout(timer);
    };
  }, [isDropdownOpen]);

  // Keyboard shortcut listeners: Cmd/Ctrl + W to close active tab, Cmd/Ctrl + T to open Get Started tab
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isCmdOrCtrl = e.metaKey || e.ctrlKey;
      if (isCmdOrCtrl && e.key.toLowerCase() === 'w') {
        e.preventDefault();
        if (activeTabId) {
          closeTab(activeTabId);
        }
      } else if (isCmdOrCtrl && e.key.toLowerCase() === 't') {
        e.preventDefault();
        setIsDropdownOpen((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTabId, closeTab]);

  // Scroll active tab into view if needed
  useEffect(() => {
    if (!scrollRef.current) return;
    const activeEl = scrollRef.current.querySelector('.tab-item--active') as HTMLElement | null;
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }, [activeTabId]);

  const filteredWorkspaces = workspaces.filter((ws) =>
    ws.name.toLowerCase().includes(searchQuery.toLowerCase().trim())
  );

  // Track collapsed state per workspace group
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [groupContextMenu, setGroupContextMenu] = useState<{
    wsId: string;
    wsName: string;
    tabIds: string[];
    x: number;
    y: number;
  } | null>(null);

  // Close group context menu on click outside
  useEffect(() => {
    if (!groupContextMenu) return;
    const handleClose = () => setGroupContextMenu(null);
    window.addEventListener('mousedown', handleClose);
    return () => window.removeEventListener('mousedown', handleClose);
  }, [groupContextMenu]);

  // Auto-expand group if active tab belongs to it.
  // Use a ref for collapsedGroups so the effect only re-runs when activeTabId or tabs change,
  // not when collapsedGroups changes — otherwise toggling collapse immediately re-expands.
  const collapsedGroupsRef = useRef(collapsedGroups);
  collapsedGroupsRef.current = collapsedGroups;

  useEffect(() => {
    if (!activeTabId) return;
    const activeTab = tabs.find((t) => t.id === activeTabId);
    if (activeTab?.workspaceId && collapsedGroupsRef.current[activeTab.workspaceId]) {
      setCollapsedGroups((prev) => ({ ...prev, [activeTab.workspaceId!]: false }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTabId, tabs]);

  const toggleGroupCollapse = (wsId: string) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [wsId]: !prev[wsId],
    }));
  };

  const closeGroup = (tabIds: string[]) => {
    tabIds.forEach((id) => closeTab(id));
    setGroupContextMenu(null);
  };

  const getTabIcon = (tab: AppTab) => {
    switch (tab.type) {
      case 'get-started':
        return 'home';
      case 'workspace':
        return 'folder';
      case 'model':
        return 'polyline';
      case 'archive':
        return 'inventory_2';
      case 'dataset':
        return 'dataset';
      default:
        return null;
    }
  };

  // Alternating two-color palette: purple then neutral, cycling per group index
  const GROUP_PALETTE = [
    { bg: 'rgba(107, 78, 230, 0.09)', border: 'rgba(107, 78, 230, 0.26)', text: '#5936d9' },
    { bg: 'rgba(0, 0, 0, 0.04)', border: 'rgba(0,0,0,0.10)', text: 'var(--color-text-secondary)' },
  ];

  // Assign palette by insertion order, not hash, so 1st group = purple, 2nd = white, etc.
  const getWorkspaceColor = (workspaceId: string, groupIndex: number) => {
    return GROUP_PALETTE[groupIndex % GROUP_PALETTE.length];
  };

  // Partition tabs into standalone tabs and workspace groups
  type TabStripItem =
    | { kind: 'standalone'; tab: AppTab }
    | {
        kind: 'group';
        workspaceId: string;
        workspaceName: string;
        color: (typeof GROUP_PALETTE)[0];
        tabs: AppTab[];
      };

  const stripItems: TabStripItem[] = [];
  const seenWorkspaces = new Set<string>();
  let groupIndex = 0;

  for (const tab of tabs) {
    if (!tab.workspaceId) {
      stripItems.push({ kind: 'standalone', tab });
    } else {
      if (seenWorkspaces.has(tab.workspaceId)) {
        continue;
      }
      seenWorkspaces.add(tab.workspaceId);
      const wsTabs = tabs.filter((t) => t.workspaceId === tab.workspaceId);
      const ws = workspaces.find((w) => w.id === tab.workspaceId);
      const wsName = ws?.name || tab.title || 'Workspace';
      const color = getWorkspaceColor(tab.workspaceId, groupIndex);
      groupIndex++;
      stripItems.push({
        kind: 'group',
        workspaceId: tab.workspaceId,
        workspaceName: wsName,
        color,
        tabs: wsTabs,
      });
    }
  }

  const renderSingleTab = (tab: AppTab, isInsideGroup = false) => {
    const isActive = tab.id === activeTabId;
    const iconName = getTabIcon(tab);
    const label = tab.type === 'get-started' ? 'Home' : tab.title;

    return (
      <div
        key={tab.id}
        className={`tab-item ${isActive ? 'tab-item--active' : ''}`}
        onClick={() => setActiveTab(tab.id)}
        onAuxClick={(e) => {
          if (e.button === 1) {
            e.preventDefault();
            closeTab(tab.id);
          }
        }}
        title={tab.type === 'get-started' ? 'Home' : tab.title}
      >
        {iconName && <span className="material-symbols-outlined tab-icon">{iconName}</span>}
        <span className="tab-label">{label}</span>
        <button
          className="tab-close-btn"
          type="button"
          title="Close Tab (Cmd+W)"
          onClick={(e) => {
            e.stopPropagation();
            closeTab(tab.id);
          }}
        >
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>
    );
  };

  return (
    <>
      <div className="tabbar-root no-drag">
        <div className="tabstrip" ref={scrollRef}>
          {stripItems.map((item) => {
            if (item.kind === 'standalone') {
              return renderSingleTab(item.tab, false);
            }

            const isCollapsed = !!collapsedGroups[item.workspaceId];
            const hasActiveTab = item.tabs.some((t) => t.id === activeTabId);

            // If only one tab in group and it's the workspace tab, render it as a plain tab (no collapse)
            if (item.tabs.length === 1 && item.tabs[0].type === 'workspace') {
              return renderSingleTab(item.tabs[0], false);
            }

            return (
              <div
                key={`group-${item.workspaceId}`}
                className={`tab-group ${isCollapsed ? 'tab-group--collapsed' : ''} ${
                  hasActiveTab ? 'tab-group--has-active' : ''
                }`}
                style={
                  {
                    '--group-bg': item.color.bg,
                    '--group-border': item.color.border,
                    '--group-text': item.color.text,
                  } as React.CSSProperties
                }
              >
                {/* Collapse/expand arrow — only toggles collapse */}
                <button
                  type="button"
                  className="tab-group-chevron-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleGroupCollapse(item.workspaceId);
                  }}
                  title={isCollapsed ? 'Expand group' : 'Collapse group'}
                >
                  <span className="material-symbols-outlined tab-group-chevron">
                    {isCollapsed ? 'chevron_right' : 'chevron_left'}
                  </span>
                </button>

                {/* Workspace name — opens the workspace tab */}
                <button
                  type="button"
                  className="tab-group-name-btn"
                  onClick={() => {
                    const wsTab = item.tabs.find((t) => t.type === 'workspace');
                    if (wsTab) setActiveTab(wsTab.id);
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setGroupContextMenu({
                      wsId: item.workspaceId,
                      wsName: item.workspaceName,
                      tabIds: item.tabs.map((t) => t.id),
                      x: e.clientX,
                      y: e.clientY,
                    });
                  }}
                  title={`Open ${item.workspaceName}`}
                >
                  <span className="tab-group-title">{item.workspaceName}</span>
                  {isCollapsed && (
                    <span className="tab-group-count">{item.tabs.length}</span>
                  )}
                </button>

                {!isCollapsed && (
                  <div className="tab-group-tabs">
                    {/* Skip the workspace tab itself — it's already represented by the group pill label */}
                    {item.tabs
                      .filter((t) => t.type !== 'workspace')
                      .map((t) => renderSingleTab(t, true))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ─── Add Button with Dropdown (outside the overflow scroll container) ─── */}
        <div className="tab-add-wrapper" ref={dropdownRef}>
          <button
            className={`tab-add-btn ${isDropdownOpen ? 'active' : ''}`}
            type="button"
            title="New Tab / Switch Workspace (Cmd+T)"
            onClick={(e) => {
              e.stopPropagation();
              setIsDropdownOpen((prev) => !prev);
            }}
          >
            <span className="material-symbols-outlined">add</span>
          </button>

          {isDropdownOpen && (
            <div
              className="tab-menu-dropdown no-drag"
              onClick={(e) => e.stopPropagation()}
              onMouseDown={(e) => e.stopPropagation()}
            >
              {/* Search box integrated at the top */}
              <div className="tab-menu-dropdown__search-wrap">
                <span className="material-symbols-outlined tab-menu-dropdown__search-icon">search</span>
                <input
                  ref={searchInputRef}
                  type="text"
                  className="tab-menu-dropdown__search-input"
                  placeholder="Search workspaces..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      setIsDropdownOpen(false);
                    }
                  }}
                />
                {searchQuery && (
                  <button
                    type="button"
                    className="tab-menu-dropdown__search-clear"
                    onClick={() => {
                      setSearchQuery('');
                      searchInputRef.current?.focus();
                    }}
                    title="Clear search"
                  >
                    <span className="material-symbols-outlined">close</span>
                  </button>
                )}
              </div>

              <div className="tab-menu-dropdown__header">
                <span>Workspaces</span>
                {workspaces.length > 0 && (
                  <span className="tab-menu-dropdown__count">{filteredWorkspaces.length}</span>
                )}
              </div>

              {/* Scrollable list showing top 10 items with scroll to see further */}
              <div className="tab-menu-dropdown__list custom-scroll">
                {workspaces.length === 0 ? (
                  <div className="tab-menu-dropdown__empty">No workspaces created yet</div>
                ) : filteredWorkspaces.length === 0 ? (
                  <div className="tab-menu-dropdown__empty">No workspaces matching "{searchQuery}"</div>
                ) : (
                  filteredWorkspaces.map((ws) => {
                    const isOpen = tabs.some(
                      (t) => t.type === 'workspace' && t.workspaceId === ws.id
                    );
                    return (
                      <button
                        key={ws.id}
                        type="button"
                        className="tab-menu-dropdown__item"
                        onClick={() => {
                          openTab({
                            type: 'workspace',
                            title: ws.name,
                            workspaceId: ws.id,
                          });
                          setIsDropdownOpen(false);
                        }}
                      >
                        <span className="material-symbols-outlined">folder</span>
                        <span className="tab-menu-dropdown__item-title">{ws.name}</span>
                        {isOpen && <span className="tab-menu-dropdown__badge">Open</span>}
                      </button>
                    );
                  })
                )}
              </div>

              <div className="tab-menu-dropdown__divider" />

              <div className="tab-menu-dropdown__footer">
                <button
                  type="button"
                  className="tab-menu-dropdown__item"
                  onClick={() => {
                    openTab({ type: 'get-started', title: 'Home' });
                    setIsDropdownOpen(false);
                  }}
                >
                  <span className="material-symbols-outlined">home</span>
                  <span className="tab-menu-dropdown__item-title">Home</span>
                </button>

                <button
                  type="button"
                  className="tab-menu-dropdown__item"
                  onClick={() => {
                    setIsDropdownOpen(false);
                    setIsWorkspaceModalOpen(true);
                  }}
                >
                  <span className="material-symbols-outlined">create_new_folder</span>
                  <span className="tab-menu-dropdown__item-title">Create Workspace...</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tab Group Context Menu */}
      {groupContextMenu && (
        <div
          className="tab-group-menu no-drag"
          style={{
            position: 'fixed',
            left: `${Math.min(groupContextMenu.x, window.innerWidth - 200)}px`,
            top: `${groupContextMenu.y + 4}px`,
            zIndex: 9999,
          }}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="tab-group-menu__header">
            <span>{groupContextMenu.wsName}</span>
          </div>
          <button
            type="button"
            className="tab-group-menu__item"
            onClick={() => {
              toggleGroupCollapse(groupContextMenu.wsId);
              setGroupContextMenu(null);
            }}
          >
            <span className="material-symbols-outlined">
              {collapsedGroups[groupContextMenu.wsId] ? 'unfold_more' : 'unfold_less'}
            </span>
            <span>{collapsedGroups[groupContextMenu.wsId] ? 'Expand Group' : 'Collapse Group'}</span>
          </button>
          <div className="tab-group-menu__divider" />
          <button
            type="button"
            className="tab-group-menu__item tab-group-menu__item--danger"
            onClick={() => closeGroup(groupContextMenu.tabIds)}
          >
            <span className="material-symbols-outlined">close</span>
            <span>Close Group ({groupContextMenu.tabIds.length} tabs)</span>
          </button>
        </div>
      )}

      <WorkspaceModal
        isOpen={isWorkspaceModalOpen}
        onClose={() => setIsWorkspaceModalOpen(false)}
      />
    </>
  );
};

export default TabBar;
