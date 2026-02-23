'use client';
import { useState } from 'react';
import ChampionInput from '@/components/ChampionInput';
import ResultCard from '@/components/ResultCard';
import ConfidenceMeter from '@/components/ConfidenceMeter';
import { mctsRecommend } from '@/lib/api';
import { ROLES, SUMMONER_SPELLS, POSITIONS, WAVE_POSITIONS } from '@/lib/champions';

const PRESETS: Record<string, Partial<GameState>> = {
  'Level 1 Start': { my_level: 1, enemy_level: 1, my_hp_pct: 100, enemy_hp_pct: 100, game_time: 90, wave_position: 'middle', my_position: 'middle' },
  'Level 3 Trading': { my_level: 3, enemy_level: 3, my_hp_pct: 80, enemy_hp_pct: 75, game_time: 210, wave_position: 'middle', my_position: 'middle' },
  'Level 6 All-in': { my_level: 6, enemy_level: 5, my_hp_pct: 85, enemy_hp_pct: 60, game_time: 420, wave_position: 'slow_push_to_them', my_position: 'extended' },
  'Mid Game': { my_level: 11, enemy_level: 10, my_hp_pct: 70, enemy_hp_pct: 70, game_time: 1200, wave_position: 'middle', my_position: 'middle' },
};

interface GameState {
  my_hp_pct: number;
  enemy_hp_pct: number;
  my_level: number;
  enemy_level: number;
  wave_position: string;
  my_position: string;
  game_time: number;
  my_mana_pct: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type MCTSResult = Record<string, any>;

export default function CoachPage() {
  const [step, setStep] = useState(0);
  const [myChamp, setMyChamp] = useState('Ahri');
  const [myRole, setMyRole] = useState('Mid');
  const [enemyChamp, setEnemyChamp] = useState('Syndra');
  const [enemyRole, setEnemyRole] = useState('Mid');
  const [summ2, setSumm2] = useState('Ignite');
  const [enemyModel, setEnemyModel] = useState('average');
  const [iterations, setIterations] = useState(1000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MCTSResult | null>(null);

  const [gs, setGs] = useState<GameState>({
    my_hp_pct: 80, enemy_hp_pct: 75, my_level: 3, enemy_level: 3,
    wave_position: 'middle', my_position: 'middle', game_time: 210, my_mana_pct: 70,
  });

  const updateGs = (k: keyof GameState, v: string | number) => setGs(prev => ({ ...prev, [k]: v }));

  const applyPreset = (name: string) => {
    const p = PRESETS[name];
    if (p) setGs(prev => ({ ...prev, ...p } as GameState));
  };

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const hpMax = 570 + (gs.my_level - 1) * 90;
      const enemyHpMax = 523 + (gs.enemy_level - 1) * 85;
      const manaMax = 418 + (gs.my_level - 1) * 25;

      const state = {
        my_champion_id: myChamp,
        my_hp: (gs.my_hp_pct / 100) * hpMax,
        my_hp_max: hpMax,
        my_mana: (gs.my_mana_pct / 100) * manaMax,
        my_mana_max: manaMax,
        my_level: gs.my_level,
        my_xp_to_next: 280,
        my_q_cd: 0, my_w_cd: 0, my_e_cd: 0, my_r_cd: gs.my_level >= 6 ? 0 : 80,
        my_flash_cd: 0, my_summ2_cd: 0,
        my_summ2_type: summ2.toLowerCase(),
        my_position: gs.my_position,
        my_gold: 500 + gs.game_time * 2,
        my_items: [],
        my_combat_power: 100 + gs.my_level * 15,
        enemy_champion_id: enemyChamp,
        enemy_hp: (gs.enemy_hp_pct / 100) * enemyHpMax,
        enemy_hp_max: enemyHpMax,
        enemy_mana_est: 200,
        enemy_level: gs.enemy_level,
        enemy_q_cd_est: 0, enemy_w_cd_est: 0, enemy_e_cd_est: 0,
        enemy_r_cd_est: gs.enemy_level >= 6 ? 0 : 80,
        enemy_flash_cd_est: 0,
        enemy_position: 'middle',
        enemy_combat_power: 100 + gs.enemy_level * 15,
        my_minions: 6, enemy_minions: 6,
        wave_position: gs.wave_position,
        is_cannon_wave: false,
        enemy_jg_last_seen: 999, enemy_jg_location: 'unknown',
        ally_jg_position: 'unknown',
        dragon_timer: 300, herald_timer: 840,
        my_tower_hp: 100, enemy_tower_hp: 100,
        game_time: gs.game_time,
        phase: gs.game_time >= 1500 ? 'late' : gs.game_time >= 840 ? 'mid' : 'early',
      };

      const res = await mctsRecommend(state, iterations, enemyModel);
      setResult(res);
      setStep(4);
    } catch (e) {
      alert('Error: ' + (e instanceof Error ? e.message : e));
    }
    setLoading(false);
  };

  const steps = ['Champion', 'Matchup', 'Game State', 'Settings', 'Results'];

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-[#f0f6fc] mb-6">🧠 Lane Coach</h1>

      {/* Step indicator */}
      <div className="flex gap-1 mb-6">
        {steps.map((s, i) => (
          <button key={s} onClick={() => i < 4 && setStep(i)}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-colors ${
              i === step ? 'bg-[#1f6feb] text-white' : i < step ? 'bg-[#1f6feb44] text-[#58a6ff]' : 'bg-[#161b22] text-[#484f58]'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Step 0: Your Champion */}
      {step === 0 && (
        <div className="space-y-4">
          <ChampionInput value={myChamp} onChange={setMyChamp} label="Your Champion" />
          <div>
            <label className="block text-xs text-[#8b949e] mb-1">Your Role</label>
            <div className="flex gap-2">
              {ROLES.map(r => (
                <button key={r} onClick={() => setMyRole(r)}
                  className={`flex-1 py-2 rounded-lg text-sm border ${myRole === r ? 'bg-[#1f6feb] text-white border-[#1f6feb]' : 'bg-[#161b22] text-[#8b949e] border-[#30363d]'}`}
                >{r}</button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[#8b949e] mb-1">Second Summoner Spell</label>
            <select value={summ2} onChange={e => setSumm2(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9]"
            >
              {SUMMONER_SPELLS.filter(s => s !== 'Flash').map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <button onClick={() => setStep(1)} className="w-full bg-[#1f6feb] text-white py-3 rounded-lg font-semibold hover:bg-[#388bfd]">Next →</button>
        </div>
      )}

      {/* Step 1: Matchup */}
      {step === 1 && (
        <div className="space-y-4">
          <ChampionInput value={enemyChamp} onChange={setEnemyChamp} label="Enemy Champion" />
          <div>
            <label className="block text-xs text-[#8b949e] mb-1">Enemy Role</label>
            <div className="flex gap-2">
              {ROLES.map(r => (
                <button key={r} onClick={() => setEnemyRole(r)}
                  className={`flex-1 py-2 rounded-lg text-sm border ${enemyRole === r ? 'bg-[#f85149] text-white border-[#f85149]' : 'bg-[#161b22] text-[#8b949e] border-[#30363d]'}`}
                >{r}</button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStep(0)} className="flex-1 bg-[#161b22] text-[#8b949e] py-3 rounded-lg border border-[#30363d]">← Back</button>
            <button onClick={() => setStep(2)} className="flex-1 bg-[#1f6feb] text-white py-3 rounded-lg font-semibold">Next →</button>
          </div>
        </div>
      )}

      {/* Step 2: Game State */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="flex gap-2 flex-wrap mb-2">
            {Object.keys(PRESETS).map(name => (
              <button key={name} onClick={() => applyPreset(name)}
                className="px-3 py-1 bg-[#161b22] border border-[#30363d] rounded-lg text-xs text-[#58a6ff] hover:border-[#58a6ff]"
              >⚡ {name}</button>
            ))}
          </div>

          {([
            ['my_hp_pct', 'Your HP %', 0, 100],
            ['enemy_hp_pct', 'Enemy HP %', 0, 100],
            ['my_mana_pct', 'Your Mana %', 0, 100],
            ['my_level', 'Your Level', 1, 18],
            ['enemy_level', 'Enemy Level', 1, 18],
            ['game_time', 'Game Time (sec)', 60, 2400],
          ] as [keyof GameState, string, number, number][]).map(([key, label, min, max]) => {
            const val = Number(gs[key]);
            return (
              <div key={key}>
                <div className="flex justify-between text-xs text-[#8b949e] mb-1">
                  <span>{label}</span>
                  <span className="text-[#f0f6fc] font-mono">{key === 'game_time' ? `${Math.floor(val / 60)}:${String(val % 60).padStart(2, '0')}` : val}</span>
                </div>
                <input type="range" min={min} max={max} value={val} onChange={e => updateGs(key, Number(e.target.value))}
                  className="w-full accent-[#58a6ff]" />
              </div>
            );
          })}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#8b949e] mb-1">Wave Position</label>
              <select value={gs.wave_position} onChange={e => updateGs('wave_position', e.target.value)}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9]"
              >
                {WAVE_POSITIONS.map(w => <option key={w} value={w}>{w.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#8b949e] mb-1">Your Position</label>
              <select value={gs.my_position} onChange={e => updateGs('my_position', e.target.value)}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-2 text-sm text-[#c9d1d9]"
              >
                {POSITIONS.map(p => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={() => setStep(1)} className="flex-1 bg-[#161b22] text-[#8b949e] py-3 rounded-lg border border-[#30363d]">← Back</button>
            <button onClick={() => setStep(3)} className="flex-1 bg-[#1f6feb] text-white py-3 rounded-lg font-semibold">Next →</button>
          </div>
        </div>
      )}

      {/* Step 3: Settings */}
      {step === 3 && (
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-[#8b949e] mb-2">Enemy Behavior Model</label>
            <div className="flex gap-2">
              {['average', 'optimal', 'passive'].map(m => (
                <button key={m} onClick={() => setEnemyModel(m)}
                  className={`flex-1 py-3 rounded-lg text-sm border capitalize ${enemyModel === m ? 'bg-[#1f6feb] text-white border-[#1f6feb]' : 'bg-[#161b22] text-[#8b949e] border-[#30363d]'}`}
                >{m}</button>
              ))}
            </div>
          </div>

          <div>
            <div className="flex justify-between text-xs text-[#8b949e] mb-1">
              <span>Simulation Iterations</span>
              <span className="text-[#f0f6fc] font-mono">{iterations}</span>
            </div>
            <input type="range" min={200} max={3000} step={100} value={iterations} onChange={e => setIterations(Number(e.target.value))}
              className="w-full accent-[#58a6ff]" />
            <p className="text-xs text-[#484f58] mt-1">More iterations = more accurate but slower</p>
          </div>

          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4 text-sm">
            <h3 className="text-[#f0f6fc] font-semibold mb-2">Summary</h3>
            <p className="text-[#8b949e]">
              <span className="text-[#58a6ff]">{myChamp}</span> ({myRole}) vs <span className="text-[#f85149]">{enemyChamp}</span> ({enemyRole})
              <br />Level {gs.my_level} vs {gs.enemy_level} · {Math.floor(Number(gs.game_time) / 60)}:{String(Number(gs.game_time) % 60).padStart(2, '0')} game time
              <br />Enemy model: {enemyModel} · {iterations} iterations
            </p>
          </div>

          <div className="flex gap-2">
            <button onClick={() => setStep(2)} className="flex-1 bg-[#161b22] text-[#8b949e] py-3 rounded-lg border border-[#30363d]">← Back</button>
            <button onClick={runAnalysis} disabled={loading}
              className="flex-1 bg-[#238636] text-white py-3 rounded-lg font-bold text-lg hover:bg-[#2ea043] disabled:opacity-50"
            >{loading ? '⏳ Analyzing...' : '🧠 ANALYZE'}</button>
          </div>
        </div>
      )}

      {/* Step 4: Results */}
      {step === 4 && result && (
        <div className="space-y-3">
          <ResultCard title="DO THIS NOW" content={result.do_this} accent="border-[#3fb950]" icon="✅" />
          <ResultCard title="WHY" content={result.why} accent="border-[#58a6ff]" icon="💡" />
          <ResultCard title="WATCH FOR" content={result.watch_for} accent="border-[#d29922]" icon="👀" />
          <ResultCard title="PLAN CHANGES IF" content={result.plan_changes_if} accent="border-[#db6d28]" icon="🔄" />
          <ConfidenceMeter label={result.confidence} />
          <ResultCard title="NEXT 2 MINUTES" content={result.next_2_min} accent="border-[#8b949e]" icon="⏱️" />

          {/* Action Scores */}
          {result.action_scores && (
            <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#8b949e] mb-3">Action Breakdown</h3>
              {Object.entries(result.action_scores as Record<string, { avg_score: number; visit_pct: number }>)
                .sort(([, a], [, b]) => b.visit_pct - a.visit_pct)
                .map(([action, data]) => (
                  <div key={action} className="mb-2">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-[#c9d1d9]">{action.replace(/_/g, ' ')}</span>
                      <span className="text-[#8b949e]">{data.visit_pct}% · score {data.avg_score}</span>
                    </div>
                    <div className="h-2 bg-[#0d1117] rounded-full overflow-hidden">
                      <div className="h-full bg-[#1f6feb] rounded-full" style={{ width: `${data.visit_pct}%` }} />
                    </div>
                  </div>
                ))}
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={() => setStep(2)} className="flex-1 bg-[#161b22] text-[#8b949e] py-3 rounded-lg border border-[#30363d]">← Edit State</button>
            <button onClick={runAnalysis} className="flex-1 bg-[#1f6feb] text-white py-3 rounded-lg font-semibold">🔄 Run Again</button>
          </div>
        </div>
      )}
    </div>
  );
}
