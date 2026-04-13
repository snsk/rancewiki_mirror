import { timingSafeEqual } from 'node:crypto';
import { createRequire } from 'node:module';

import { next, rewrite } from '@vercel/functions';

const require = createRequire(import.meta.url);
const routeMap = new Map(Object.entries(require('./vercel-routes.json')));

const BASIC_REALM = 'Rance Wiki Mirror';

function normalizePath(pathname) {
  if (pathname === '/') {
    return pathname;
  }
  return pathname.endsWith('/') ? pathname : `${pathname}/`;
}

function buildInternalPath(relativePath) {
  const normalized = relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
  return `/rance-world-note/${normalized}`;
}

function secureEqual(left, right) {
  const leftBytes = Buffer.from(left, 'utf8');
  const rightBytes = Buffer.from(right, 'utf8');
  if (leftBytes.length !== rightBytes.length) {
    return false;
  }
  return timingSafeEqual(leftBytes, rightBytes);
}

function parseBasicAuth(request) {
  const authorization = request.headers.get('authorization');
  if (!authorization || !authorization.startsWith('Basic ')) {
    return null;
  }

  try {
    const decoded = Buffer.from(authorization.slice(6), 'base64').toString('utf8');
    const separatorIndex = decoded.indexOf(':');
    if (separatorIndex === -1) {
      return null;
    }
    return {
      username: decoded.slice(0, separatorIndex),
      password: decoded.slice(separatorIndex + 1),
    };
  } catch {
    return null;
  }
}

function unauthorizedResponse() {
  return new Response('Authentication required.', {
    status: 401,
    headers: {
      'Cache-Control': 'no-store',
      'Content-Type': 'text/plain; charset=utf-8',
      'WWW-Authenticate': `Basic realm="${BASIC_REALM}", charset="UTF-8"`,
    },
  });
}

function misconfiguredResponse() {
  return new Response('Missing BASIC_AUTH_USERNAME or BASIC_AUTH_PASSWORD.', {
    status: 500,
    headers: {
      'Cache-Control': 'no-store',
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}

function isAuthorized(request, username, password) {
  const credentials = parseBasicAuth(request);
  if (!credentials) {
    return false;
  }
  return secureEqual(credentials.username, username) && secureEqual(credentials.password, password);
}

export default function middleware(request) {
  const expectedUsername = process.env.BASIC_AUTH_USERNAME;
  const expectedPassword = process.env.BASIC_AUTH_PASSWORD;

  if (!expectedUsername || !expectedPassword) {
    return misconfiguredResponse();
  }

  if (!isAuthorized(request, expectedUsername, expectedPassword)) {
    return unauthorizedResponse();
  }

  const url = new URL(request.url);

  if (url.pathname === '/') {
    return Response.redirect(new URL('/rance-world-note/', url), 307);
  }

  if (url.pathname === '/assets' || url.pathname.startsWith('/assets/')) {
    url.pathname = `/rance-world-note${url.pathname}`;
    return rewrite(url);
  }

  // Clean wiki URLs are mapped back to the hashed static files produced by the mirror builder.
  const routeTarget = routeMap.get(normalizePath(url.pathname));
  if (routeTarget) {
    url.pathname = buildInternalPath(routeTarget);
    return rewrite(url);
  }

  return next();
}

export const config = {
  runtime: 'nodejs',
  matcher: ['/', '/assets', '/assets/:path*', '/rance-world-note', '/rance-world-note/:path*'],
};
