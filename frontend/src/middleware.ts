import { NextRequest, NextResponse } from 'next/server';

const SUPPORTED_LOCALES = ['en', 'ca'];
const DEFAULT_LOCALE = 'en';

function detectLocale(acceptLanguage: string | null): string {
  if (!acceptLanguage) return DEFAULT_LOCALE;
  const languages = acceptLanguage.split(',').map((lang) => {
    const [code] = lang.trim().split(';');
    return code.trim().split('-')[0].toLowerCase();
  });
  for (const lang of languages) {
    if (SUPPORTED_LOCALES.includes(lang)) return lang;
  }
  return DEFAULT_LOCALE;
}

export function middleware(request: NextRequest) {
  const host = request.headers.get('host') ?? '';

  // Redirect bare domain to play.meeple.cat
  if (host === 'meeple.cat' || host === 'www.meeple.cat') {
    const url = new URL(request.url);
    url.host = 'play.meeple.cat';
    url.protocol = 'https';
    return NextResponse.redirect(url, 301);
  }

  const response = NextResponse.next();

  // Set locale cookie if not already present
  if (!request.cookies.get('NEXT_LOCALE')) {
    const acceptLanguage = request.headers.get('accept-language');
    const locale = detectLocale(acceptLanguage);
    response.cookies.set('NEXT_LOCALE', locale, {
      path: '/',
      maxAge: 60 * 60 * 24 * 365,
      sameSite: 'lax',
    });
  }

  return response;
}

export const config = {
  matcher: [
    // Run on all routes except static files and Next.js internals
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
