import type { Metadata, Viewport } from 'next';
import './globals.css';
import './workspace.css';
import MobileViewport from '../components/mobile-viewport';
import { assistantName } from '../lib/persona';

export const viewport: Viewport = {width:"device-width",initialScale:1,viewportFit:"cover",themeColor:"#121116"};

export const metadata: Metadata = {
  manifest:"/manifest.webmanifest",
  appleWebApp:{capable:true,title:"Ariana",statusBarStyle:"black-translucent"},
  icons:{apple:[{url:"/app-icon",sizes:"512x512",type:"image/png"}]},
  referrer:"no-referrer",
  title: `${assistantName} — Your personal assistant`,
  description: `${assistantName}. A quiet presence. Speak, create and get things done.`,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><MobileViewport/>{children}</body></html>;
}
