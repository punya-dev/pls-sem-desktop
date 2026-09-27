import React, { useState, useRef, useEffect } from 'react';
import { useStore } from '../store';
import type { NodeData } from '../store';

interface NodeProps {
  node: NodeData;
  isSelected: boolean;
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerUp: (e: React.PointerEvent) => void;
}

const Node = ({ node, isSelected, onPointerDown, onPointerUp }: NodeProps) => {
  const { updateNode } = useStore();
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
  };

  const handleBlur = () => {
    setIsEditing(false);
    if (inputRef.current) {
      updateNode(node.id, { label: inputRef.current.value });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleBlur();
    }
  };

  const renderShape = () => {
    if (node.isText) {
      return null;
    }

    if (!node.isLatent) {
      // Indicator variable (Rectangle)
      const w = node.width || 64;
      const h = node.height || 24;
      return <rect x={-w/2} y={-h/2} width={w} height={h} rx={2} fill="#fef08a" stroke="#ca8a04" strokeWidth={1} />;
    }

    const size = node.width || 72; // default latent size 72 (radius 36)
    const r = size / 2;
    const fill = node.fillColor || '#ffffff';
    const stroke = 'var(--color-text-secondary)';
    const shapeProps = {
      fill: fill,
      stroke: stroke,
      strokeWidth: 2,
    };

    switch (node.shape) {
      case 'rect':
        return <rect x={-r} y={-r} width={size} height={size} rx={8} {...shapeProps} />;
      case 'hexagon':
        return (
          <polygon 
            points={`0,${-r} ${r*0.866},${-r/2} ${r*0.866},${r/2} 0,${r} ${-r*0.866},${r/2} ${-r*0.866},${-r/2}`}
            {...shapeProps} 
          />
        );
      case 'octagon':
        const o = r * 0.414;
        return (
          <polygon 
            points={`${o},${-r} ${r},${-o} ${r},${o} ${o},${r} ${-o},${r} ${-r},${o} ${-r},${-o} ${-o},${-r}`}
            {...shapeProps} 
          />
        );
      case 'circle':
      default:
        return <circle cx={0} cy={0} r={r} {...shapeProps} />;
    }
  };

  // Text formatting styles
  const isIndicator = !node.isLatent && !node.isText;
  
  const textStyle = {
    fontWeight: node.bold ? 'bold' : (isIndicator ? 'normal' : '600'),
    fontStyle: node.italic ? 'italic' : 'normal',
    textDecoration: node.underline ? 'underline' : 'none',
    fontSize: isIndicator ? '10px' : `${node.fontSize || 14}px`,
    fontFamily: isIndicator ? 'var(--font-mono)' : 'var(--font-sans)',
    userSelect: 'none' as const,
    fill: isIndicator ? '#422006' : (node.isText ? (node.fillColor || 'var(--color-text-primary)') : 'var(--color-text-primary)'),
    pointerEvents: 'none' as const
  };

  const wSize = node.isLatent ? (node.width || 72) : (node.width || 64);
  const hSize = node.isLatent ? wSize : (node.height || 24);

  return (
    <g 
      transform={`translate(${node.x}, ${node.y})`}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onDoubleClick={handleDoubleClick}
      style={{ cursor: 'pointer' }}
    >
      {/* Selection Border (Purple Dotted) */}
      {isSelected && (
        node.isLatent && node.shape !== 'rect' ? (
          <circle 
            cx={0} 
            cy={0} 
            r={(wSize/2) + 8} 
            fill="none" 
            stroke="var(--color-accent, #6B4EE6)" 
            strokeWidth="2" 
            strokeDasharray="6 6" 
          />
        ) : (
          <rect 
            x={-(wSize/2 + 8)} 
            y={-(hSize/2 + 8)} 
            width={wSize + 16} 
            height={hSize + 16} 
            rx={4}
            fill="none" 
            stroke="var(--color-accent, #6B4EE6)" 
            strokeWidth="2" 
            strokeDasharray="6 6" 
          />
        )
      )}
      
      {/* Shape */}
      {renderShape()}
      
      {/* Text / Input */}
      {isEditing ? (
        <foreignObject x={-wSize/2} y={-15} width={wSize} height={30}>
          <input 
            ref={inputRef}
            defaultValue={node.label}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
            className="w-full text-center bg-transparent border-none outline-none"
            style={{ 
              ...textStyle,
              pointerEvents: 'auto',
              color: textStyle.fill
            }}
          />
        </foreignObject>
      ) : (
        <text 
          textAnchor="middle" 
          dominantBaseline="central"
          y={node.isLatent ? 60 : 1}
          style={textStyle}
        >
          {node.label}
        </text>
      )}
    </g>
  );
};

export default Node;
