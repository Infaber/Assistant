import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Ariana — Your personal assistant',
  description: 'Ariana. A quiet presence. Speak, create and get things done.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
