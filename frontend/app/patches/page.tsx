'use client';
import { useState, useEffect } from 'react';
import RoleTabs from '@/components/RoleTabs';
import { getPatches, getPatch, getPatchByRole, decodePatch } from '@/lib/api';

interface PatchInfo { patch_version: string; url: string; extracted_at: string }
interface Change { change_type: string; target_name: string; ability?: string; description: string; impact_score?: number; roles_affected?: string[] }

export default function PatchesPage() {
  const [patches, setPatches] = useState<PatchInfo[]>([]);
  const [selected, setSelected] = useState('');
  const [role, setRole] = useState('all');
  const [changes, setChanges] = useState<Change[]>([]);
  const [tldr, setTldr] = useState('');
  const [decoding, setDecoding] = useState(false);

  useEffect(() => { getPatches().then(p => { if (Array.isArray(p)) setPatches(p); }); }, []);

  useEffect(() => {
    if (!selected) return;
    if (role === 'all') {
      getPatch(selected).then(d => { setChanges(d.changes || []); setTldr(''); });
    } else {
      getPatchByRole(selected, role).then(d => {
        const all = [
          ...(d.buffs || []).map((b: Record<string, unknown>) => ({ ...b, change_type: 'champion_buff', target_name: b.target, description: b.description })),
          ...(d.nerfs || []).map((n: Record<string, unknown>) => ({ ...n, change_type: 'champion_nerf', target_name: n.target, description: n.description })),
          ...(d.item_changes || []).map((i: Record<string, unknown>) => ({ ...i, change_type: 'item_change', target_name: i.target, description: i.description })),
          ...(d.system_changes || []).map((s: Record<string, unknown>) => ({ ...s, change_type: 'system_change', target_name: s.target, description: s.description })),
        ];
        setChanges(all as Change[]);
        setTldr(d.tldr || '');
      });
    }
  }, [selected, role]);

  const handleDecode = async () => {
    setDecoding(true);
    try {
      const res = await decodePatch();
      if (res.error) { alert(res.error); } else {
        const p = await getPatches();
        if (Array.isArray(p)) setPatches(p);
        setSelected(res.patch_version);
      }
    } catch (e) { alert('Error: ' + (e instanceof Error ? e.message : e)); }
    setDecoding(false);
  };

  const borderColor = (type: string) => {
    if (type.includes('buff')) return 'border-[#3fb950]';
    if (type.includes('nerf')) return 'border-[#f85149]';
    if (type.includes('item')) return 'border-[#d29922]';
    return 'border-[#8b949e]';
  };

  const buffs = changes.filter(c => c.change_type?.includes('buff'));
  const nerfs = changes.filter(c => c.change_type?.includes('nerf'));
  const items = changes.filter(c => c.change_type === 'item_change');
  const system = changes.filter(c => c.change_type === 'system_change');

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-[#f0f6fc] mb-6">📋 Patch Decoder</h1>

      <div className="flex gap-3 items-center mb-4">
        <select value={selected} onChange={e => setSelected(e.target.value)}
          className="bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9]"
        >
          <option value="">Select patch...</option>
          {patches.map(p => <option key={p.patch_version} value={p.patch_version}>Patch {p.patch_version}</option>)}
        </select>
        <button onClick={handleDecode} disabled={decoding}
          className="bg-[#238636] text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-[#2ea043] disabled:opacity-50"
        >{decoding ? '⏳ Decoding...' : '⚡ Decode Latest'}</button>
      </div>

      <RoleTabs active={role} onChange={setRole} />

      {tldr && (
        <div className="bg-[#1c2128] border border-[#30363d] rounded-lg p-4 mt-4 text-sm text-[#c9d1d9]">
          📋 {tldr}
        </div>
      )}

      {!tldr && selected && (
        <div className="bg-[#1c2128] border border-[#30363d] rounded-lg p-4 mt-4 text-sm text-[#c9d1d9]">
          📋 {buffs.length} buffs · {nerfs.length} nerfs · {items.length} item changes · {system.length} system changes
        </div>
      )}

      <div className="mt-4 space-y-2">
        {changes.length === 0 && selected && (
          <p className="text-[#484f58] text-center py-8">No changes found for this filter.</p>
        )}
        {!selected && (
          <p className="text-[#484f58] text-center py-8">Select a patch or decode the latest one to get started.</p>
        )}
        {changes.map((c, i) => (
          <div key={i} className={`bg-[#161b22] border-l-4 ${borderColor(c.change_type)} rounded-lg p-3`}>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[#f0f6fc]">{c.target_name}</span>
              {c.ability && <span className="text-xs text-[#8b949e]">— {c.ability}</span>}
              {c.impact_score != null && c.impact_score !== 0 && (
                <span className={`text-xs px-2 py-0.5 rounded ${
                  c.impact_score > 0 ? 'bg-[#1a4d2e] text-[#3fb950]' : 'bg-[#4d1a1a] text-[#f85149]'
                }`}>
                  {c.impact_score > 0 ? '+' : ''}{c.impact_score}
                </span>
              )}
            </div>
            {c.description && <p className="text-xs text-[#c9d1d9] mt-1">{c.description}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
