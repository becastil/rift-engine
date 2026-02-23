'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

const NAV = [
  { href: '/', icon: '🏠', label: 'Home' },
  { href: '/coach', icon: '🧠', label: 'Coach' },
  { href: '/simulate', icon: '⚔️', label: 'Simulate' },
  { href: '/patches', icon: '📋', label: 'Patches' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed top-4 left-4 z-50 md:hidden bg-[#161b22] border border-[#30363d] rounded-lg p-2 text-xl"
      >
        {open ? '✕' : '☰'}
      </button>

      {/* Sidebar */}
      <aside className={`
        fixed top-0 left-0 h-full w-56 bg-[#161b22] border-r border-[#30363d] z-40
        flex flex-col pt-6 transition-transform duration-200
        ${open ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0
      `}>
        <div className="px-5 mb-8">
          <h1 className="text-xl font-bold text-[#58a6ff]">⚡ Rift Engine</h1>
          <p className="text-xs text-[#8b949e] mt-1">LoL Coaching Platform</p>
        </div>

        <nav className="flex-1">
          {NAV.map(({ href, icon, label }) => {
            const active = pathname === href || (href !== '/' && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className={`
                  flex items-center gap-3 px-5 py-3 text-sm transition-colors
                  ${active
                    ? 'bg-[#1f6feb22] text-[#58a6ff] border-r-2 border-[#58a6ff]'
                    : 'text-[#8b949e] hover:text-[#c9d1d9] hover:bg-[#1c2128]'
                  }
                `}
              >
                <span className="text-lg">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="px-5 py-4 text-xs text-[#484f58] border-t border-[#30363d]">
          Rift Engine v0.2
        </div>
      </aside>

      {/* Overlay for mobile */}
      {open && (
        <div className="fixed inset-0 bg-black/50 z-30 md:hidden" onClick={() => setOpen(false)} />
      )}
    </>
  );
}
