import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Ariana — Your personal assistant',
  description: 'Your personal intelligence workspace. Speak, explore and get things done with Ariana.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
