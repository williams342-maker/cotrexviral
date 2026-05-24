import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  metadataBase: new URL('https://cortexviral.com'),
  title: {
    default: 'CortexViral — AI Viral Content Engine for TikTok, Reels & Shorts',
    template: '%s | CortexViral',
  },
  description:
    'CortexViral helps creators, startups, and brands generate viral hooks, scripts, and short-form content engineered for TikTok, Instagram Reels, and YouTube Shorts.',
  applicationName: 'CortexViral',
  keywords: [
    'AI viral content generator',
    'TikTok hooks AI',
    'Instagram Reels scripts',
    'YouTube Shorts ideas',
    'AI content for creators',
  ],
  openGraph: {
    type: 'website',
    siteName: 'CortexViral',
    title: 'CortexViral — AI Viral Content Engine',
    description: 'Generate hooks, scripts, and short-form content built for virality.',
    url: 'https://cortexviral.com',
    images: [{ url: '/cortex-logo.png', width: 512, height: 512, alt: 'CortexViral' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'CortexViral — AI Viral Content Engine',
    description: 'Generate hooks, scripts, and short-form content built for virality.',
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
