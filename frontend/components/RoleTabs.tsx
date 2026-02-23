'use client';

const TABS = [
  { key: 'all', label: 'All', icon: '🎯' },
  { key: 'top', label: 'Top', icon: '🛡️' },
  { key: 'jungle', label: 'Jungle', icon: '🌿' },
  { key: 'mid', label: 'Mid', icon: '🔮' },
  { key: 'adc', label: 'ADC', icon: '🏹' },
  { key: 'support', label: 'Support', icon: '💫' },
];

interface Props {
  active: string;
  onChange: (role: string) => void;
}

export default function RoleTabs({ active, onChange }: Props) {
  return (
    <div className="flex gap-2 flex-wrap">
      {TABS.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
            active === t.key
              ? 'bg-[#1f6feb] text-white border-[#1f6feb]'
              : 'bg-[#161b22] text-[#8b949e] border-[#30363d] hover:border-[#58a6ff] hover:text-[#c9d1d9]'
          }`}
        >
          {t.icon} {t.label}
        </button>
      ))}
    </div>
  );
}
