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
      default:
        return null;
    }
  };

  return (
    <>
      <div className="tabbar-root no-drag">
        <div className="tabstrip" ref={scrollRef}>
          {tabs.map((tab) => {
            const isActive = tab.id === activeTabId;
            const iconName = getTabIcon(tab);

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
                <span className="tab-label">{tab.type === 'get-started' ? 'Home' : tab.title}</span>
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

      <WorkspaceModal
        isOpen={isWorkspaceModalOpen}
        onClose={() => setIsWorkspaceModalOpen(false)}
      />
    </>
  );
};

export default TabBar;
