import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const host = request.headers.get('host') ?? '';

  // Redirect bare domain to play.meeple.cat
  if (host === 'meeple.cat' || host === 'www.meeple.cat') {
    const url = new URL(request.url);
    url.host = 'play.meeple.cat';
    url.protocol = 'https';
    return NextResponse.redirect(url, 301);
  }

  return NextResponse.next();
}
