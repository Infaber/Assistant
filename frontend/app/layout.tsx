import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Ariana — Your space to think',
  description: 'Talk, explore, and think things through with your personal voice assistant.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
