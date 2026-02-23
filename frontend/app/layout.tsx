import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'Rift Engine',
  description: 'League of Legends Coaching Platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Sidebar />
        <main className="md:ml-56 min-h-screen p-6 pt-16 md:pt-6">
          {children}
        </main>
      </body>
    </html>
  );
}
