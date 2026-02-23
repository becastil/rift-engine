'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getHealth } from '@/lib/api';

const CARDS = [
  { href: '/coach', icon: '🧠', title: 'Coach', desc: 'Get real-time lane advice from the MCTS engine. Pick your matchup, set the game state, and get recommendations an 8th grader can follow.' },
  { href: '/simulate', icon: '⚔️', title: 'Simulate', desc: 'Run a full match simulation with any 10-champion draft. See gold curves, timelines, and minute-by-minute champion deep dives.' },
  { href: '/patches', icon: '📋', title: 'Patches', desc: 'Decode the latest patch notes with AI. See buffs, nerfs, and item changes filtered by your role.' },
];

export default function Home() {
  const [status, setStatus] = useState<string>('checking...');

  useEffect(() => {
    getHealth()
      .then(d => setStatus(d.status === 'ok' ? '🟢 Online' : '🔴 Error'))
      .catch(() => setStatus('🔴 Offline'));
  }, []);

  return (
    <div className="max-w-3xl">
      <h1 className="text-3xl font-bold text-[#f0f6fc] mb-2">⚡ Rift Engine</h1>
      <p className="text-[#8b949e] mb-1">League of Legends Coaching Platform</p>
      <p className="text-xs text-[#484f58] mb-8">Backend: {status}</p>

      <div className="grid gap-4">
        {CARDS.map(c => (
          <Link key={c.href} href={c.href} className="block bg-[#161b22] border border-[#30363d] rounded-xl p-5 hover:border-[#58a6ff] transition-colors group">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-2xl">{c.icon}</span>
              <h2 className="text-lg font-semibold text-[#f0f6fc] group-hover:text-[#58a6ff] transition-colors">{c.title}</h2>
            </div>
            <p className="text-sm text-[#8b949e]">{c.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
