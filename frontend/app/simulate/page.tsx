'use client';
import { useState } from 'react';
import ChampionInput from '@/components/ChampionInput';
import { simulate } from '@/lib/api';
import { ROLES } from '@/lib/champions';

const DEFAULTS = {
  blue: ['Renekton', 'LeeSin', 'Ahri', 'Jinx', 'Thresh'],
  red: ['Gnar', 'Viego', 'Syndra', 'Kaisa', 'Nautilus'],
};

interface Pick { champion_id: string; role: string }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SimResult = Record<string, any>;

export default function SimulatePage() {
  const [blueTeam, setBlueTeam] = useState('T1');
  const [redTeam, setRedTeam] = useState('Gen.G');
  const [blue, setBlue] = useState<Pick[]>(ROLES.map((r, i) => ({ champion_id: DEFAULTS.blue[i], role: r.toLowerCase() })));
  const [red, setRed] = useState<Pick[]>(ROLES.map((r, i) => ({ champion_id: DEFAULTS.red[i], role: r.toLowerCase() })));
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SimResult | null>(null);
  const [deepDive, setDeepDive] = useState('');

  const updatePick = (side: 'blue' | 'red', idx: number, champ: string) => {
    const setter = side === 'blue' ? setBlue : setRed;
    setter(prev => prev.map((p, i) => i === idx ? { ...p, champion_id: champ } : p));
  };

  const run = async () => {
    setLoading(true);
    try {
      const res = await simulate({
        blue_team_id: blueTeam, red_team_id: redTeam,
        blue_draft: blue, red_draft: red,
        seed: Math.floor(Math.random() * 100000),
      });
      setResult(res);
      const keys = Object.keys(res.champion_reports || {});
      if (keys.length) setDeepDive(keys[0]);
    } catch (e) { alert('Error: ' + (e instanceof Error ? e.message : e)); }
    setLoading(false);
  };

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-[#f0f6fc] mb-6">⚔️ Match Simulation</h1>

      <div className="grid md:grid-cols-2 gap-4 mb-4">
        {/* Blue team */}
        <div className="bg-[#161b22] border-l-4 border-[#58a6ff] rounded-lg p-4">
          <input value={blueTeam} onChange={e => setBlueTeam(e.target.value)}
            className="bg-transparent border-none text-[#58a6ff] font-bold text-lg mb-3 outline-none w-full" />
          {blue.map((p, i) => (
            <div key={i} className="flex items-center gap-2 mb-2">
              <span className="text-xs text-[#8b949e] w-16">{ROLES[i]}</span>
              <ChampionInput value={p.champion_id} onChange={v => updatePick('blue', i, v)} />
            </div>
          ))}
        </div>

        {/* Red team */}
        <div className="bg-[#161b22] border-l-4 border-[#f85149] rounded-lg p-4">
          <input value={redTeam} onChange={e => setRedTeam(e.target.value)}
            className="bg-transparent border-none text-[#f85149] font-bold text-lg mb-3 outline-none w-full" />
          {red.map((p, i) => (
            <div key={i} className="flex items-center gap-2 mb-2">
              <span className="text-xs text-[#8b949e] w-16">{ROLES[i]}</span>
              <ChampionInput value={p.champion_id} onChange={v => updatePick('red', i, v)} />
            </div>
          ))}
        </div>
      </div>

      <button onClick={run} disabled={loading}
        className="w-full bg-[#1f6feb] text-white py-3 rounded-lg font-bold text-lg hover:bg-[#388bfd] disabled:opacity-50 mb-6"
      >{loading ? '⏳ Simulating...' : '⚔️ SIMULATE MATCH'}</button>

      {result && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-[#161b22] rounded-lg p-4 text-center border border-[#30363d]">
              <div className={`text-2xl font-bold ${result.winner === 'blue' ? 'text-[#58a6ff]' : 'text-[#f85149]'}`}>
                {result.winner?.toUpperCase()}
              </div>
              <div className="text-xs text-[#8b949e]">Winner</div>
            </div>
            <div className="bg-[#161b22] rounded-lg p-4 text-center border border-[#30363d]">
              <div className="text-2xl font-bold text-[#f0f6fc]">{result.duration_minutes}m</div>
              <div className="text-xs text-[#8b949e]">Duration</div>
            </div>
            <div className="bg-[#161b22] rounded-lg p-4 text-center border border-[#30363d]">
              <div className="text-2xl font-bold text-[#58a6ff]">{(result.blue_win_probability * 100).toFixed(1)}%</div>
              <div className="text-xs text-[#8b949e]">Blue Win %</div>
            </div>
          </div>

          {/* Gold Curve - simple text-based since we skip recharts dep issues */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
            <h3 className="text-sm font-semibold text-[#f0f6fc] mb-3">Gold Differential</h3>
            <div className="space-y-1">
              {(result.gold_curve || []).filter((_: unknown, i: number) => i % 5 === 0).map((g: { time: number; gold_diff: number }, i: number) => {
                const maxDiff = Math.max(...(result.gold_curve || []).map((x: { gold_diff: number }) => Math.abs(x.gold_diff)), 1);
                const pct = Math.abs(g.gold_diff) / maxDiff * 100;
                const isBlue = g.gold_diff >= 0;
                return (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="w-10 text-[#8b949e] text-right">{Math.floor(g.time / 60)}m</span>
                    <div className="flex-1 flex items-center">
                      <div className="w-1/2 flex justify-end">
                        {!isBlue && <div className="h-3 bg-[#f85149] rounded-l" style={{ width: `${pct}%` }} />}
                      </div>
                      <div className="w-px h-4 bg-[#30363d]" />
                      <div className="w-1/2">
                        {isBlue && <div className="h-3 bg-[#58a6ff] rounded-r" style={{ width: `${pct}%` }} />}
                      </div>
                    </div>
                    <span className={`w-16 text-right ${isBlue ? 'text-[#58a6ff]' : 'text-[#f85149]'}`}>
                      {isBlue ? '+' : ''}{g.gold_diff.toLocaleString()}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Timeline */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4 max-h-72 overflow-y-auto">
            <h3 className="text-sm font-semibold text-[#f0f6fc] mb-3">Timeline</h3>
            {(result.timeline || []).map((e: { time: number; description: string; event_type: string }, i: number) => (
              <div key={i} className="flex gap-2 py-1 border-b border-[#21262d] text-xs">
                <span className="text-[#58a6ff] font-mono w-12">{(e.time / 60).toFixed(1)}m</span>
                <span className="text-[#c9d1d9]">{e.description}</span>
              </div>
            ))}
          </div>

          {/* Champion Deep Dive */}
          {result.champion_reports && Object.keys(result.champion_reports).length > 0 && (
            <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#f0f6fc] mb-3">Champion Deep Dive</h3>
              <select value={deepDive} onChange={e => setDeepDive(e.target.value)}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9] mb-3">
                {Object.keys(result.champion_reports).map(k => <option key={k} value={k}>{k}</option>)}
              </select>
              <div className="max-h-64 overflow-y-auto space-y-2">
                {(result.champion_reports[deepDive] || []).map((r: { minute: number; action: string; reasoning: string; level: number; kda: string; gold: number; cs: number }, i: number) => (
                  <div key={i} className="border-b border-[#21262d] pb-2 text-xs">
                    <div className="flex gap-2">
                      <span className="text-[#58a6ff] font-mono w-10">{r.minute}m</span>
                      <span className="text-[#f0f6fc] font-semibold">{r.action}</span>
                    </div>
                    <div className="text-[#8b949e] ml-12">L{r.level} · KDA {r.kda} · {Math.round(r.gold)}g · CS {r.cs}</div>
                    <div className="text-[#c9d1d9] ml-12 mt-1">{r.reasoning}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
