import React, { useState } from 'react';
import { useStore } from '../store';

const Sidebar = () => {
  const { variables } = useStore();
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({});

  const toggleCategory = (cat: string) => {
    setCollapsedCategories(prev => ({ ...prev, [cat]: !prev[cat] }));
  };

  // Group variables by category
  const categories = Array.from(new Set(variables.map(v => v.category)));

  return (
    <aside className="var-sidebar" id="var-sidebar">
      <div className="var-sidebar__search">
        <div className="var-sidebar__search-inner">
          <svg className="var-sidebar__search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" className="var-sidebar__search-input" placeholder="Filter variables... (⌘F)" />
        </div>
      </div>
      <div className="var-sidebar__header">
        <span className="var-sidebar__header-label">survey_data.csv</span>
        <div style={{'display': 'flex', 'alignItems': 'center', 'gap': '6px'}}>
          <span className="var-sidebar__count">24 vars</span>
          <span className="var-sidebar__collapse-all" id="collapse-all-btn">Collapse</span>
        </div>
      </div>
      
      <div className="var-sidebar__list" id="var-list">
        {categories.map(cat => {
          const catVars = variables.filter(v => v.category === cat);
          const isCollapsed = collapsedCategories[cat];
          return (
            <div key={cat} className="var-cat">
              <div className="var-cat__header" onClick={() => toggleCategory(cat)}>
                <div className="var-cat__header-left">
                  <svg className={`cat-chevron ${isCollapsed ? 'rotated' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                  <span className="var-cat__name">{cat}</span>
                </div>
                <span className="var-cat__count">{catVars.length}</span>
              </div>
              <div className={`var-items ${isCollapsed ? 'hidden' : ''}`}>
                {catVars.map(v => (
                  <div key={v.id} className="var-item" draggable onDragStart={(e) => {
                    e.dataTransfer.effectAllowed = 'copy';
                    e.dataTransfer.setData('text/plain', v.name);
                  }}>
                    <span className="var-item__name">{v.name}</span>
                    <span className="var-item__type">{v.type}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
};

export default Sidebar;
