import React, { useState, useRef, useEffect } from 'react';

interface EditableCellProps {
  value: string | number;
  onChange: (val: string) => void;
  type?: 'text' | 'number';
  className?: string;
  disabled?: boolean;
}

export const EditableCell: React.FC<EditableCellProps> = ({ value, onChange, type = 'text', className = '', disabled = false }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [tempValue, setTempValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTempValue(value);
  }, [value]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  const commit = () => {
    setIsEditing(false);
    if (tempValue !== value) {
      onChange(tempValue.toString());
    }
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type={type}
        value={tempValue}
        onChange={e => setTempValue(e.target.value)}
        onBlur={commit}
        onKeyDown={e => e.key === 'Enter' && commit()}
        className={`w-full bg-white border border-indigo-500 rounded shadow-sm outline-none px-1 py-0.5 m-[-2px] text-slate-900 ${className}`}
      />
    );
  }

  return (
    <span 
      onClick={() => !disabled && setIsEditing(true)} 
      className={`block w-full truncate ${!disabled ? 'cursor-text hover:bg-slate-100 rounded' : ''} ${className}`}
      title={!disabled ? "Click to edit" : undefined}
    >
      {value}
    </span>
  );
};
