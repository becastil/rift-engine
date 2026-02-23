'use client';
import { useState, useRef } from 'react';
import { CHAMPIONS } from '@/lib/champions';

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  label?: string;
}

export default function ChampionInput({ value, onChange, placeholder = 'Champion...', label }: Props) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  const filtered = CHAMPIONS.filter(c =>
    c.toLowerCase().includes((filter || value).toLowerCase())
  ).slice(0, 8);

  return (
    <div className="relative" ref={ref}>
      {label && <label className="block text-xs text-[#8b949e] mb-1">{label}</label>}
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={e => { onChange(e.target.value); setFilter(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9] focus:border-[#58a6ff] outline-none"
      />
      {open && filtered.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-[#161b22] border border-[#30363d] rounded-lg shadow-lg z-10 max-h-48 overflow-y-auto">
          {filtered.map(c => (
            <button
              key={c}
              onMouseDown={() => { onChange(c); setOpen(false); }}
              className="block w-full text-left px-3 py-2 text-sm text-[#c9d1d9] hover:bg-[#1f6feb33] transition-colors"
            >
              {c}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
