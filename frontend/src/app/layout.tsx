import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'IMDb Video Generator',
  description: 'AI-powered IMDb-to-video generation workflow',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
