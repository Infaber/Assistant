import type { Metadata } from 'next';
import './globals.css';
import { assistantName } from '../lib/persona';

export const metadata: Metadata = {
  title: `${assistantName} — Your personal assistant`,
  description: `${assistantName}. A quiet presence. Speak, create and get things done.`,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
