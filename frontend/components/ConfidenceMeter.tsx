interface Props {
  label: string; // e.g. "HIGH (78%)"
}

export default function ConfidenceMeter({ label }: Props) {
  // Parse percentage from label
  const match = label.match(/(\d+)%/);
  const pct = match ? parseInt(match[1]) : 50;

  const color = pct >= 60 ? 'bg-[#3fb950]' : pct >= 35 ? 'bg-[#d29922]' : 'bg-[#f85149]';

  return (
    <div className="bg-[#161b22] rounded-lg p-4 border border-[#30363d]">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-[#8b949e]">Confidence</span>
        <span className="text-sm font-bold text-[#f0f6fc]">{label}</span>
      </div>
      <div className="h-3 bg-[#0d1117] rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
