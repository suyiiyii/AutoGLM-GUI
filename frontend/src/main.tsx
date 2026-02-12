import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider, createRouter } from '@tanstack/react-router';
import { routeTree } from './routeTree.gen';
import { I18nProvider } from './lib/i18n-context';
import { ThemeProvider } from './lib/theme-provider';
import './styles.css';

window.addEventListener('error', event => {
  const errorObj = event.error;
  console.error('[GlobalError]', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    stack: errorObj instanceof Error ? errorObj.stack : undefined,
  });
});

window.addEventListener('unhandledrejection', event => {
  const reason = event.reason;
  if (reason instanceof Error) {
    console.error('[UnhandledRejection]', {
      message: reason.message,
      stack: reason.stack,
    });
  } else {
    console.error('[UnhandledRejection]', reason);
  }
});

// Set up a Router instance
const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  scrollRestoration: true,
});

// Register things for typesafety
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

const rootElement = document.getElementById('app');

if (rootElement && !rootElement.innerHTML) {
  const root = ReactDOM.createRoot(rootElement);
  try {
    root.render(
      <ThemeProvider
        attribute="class"
        defaultTheme="light"
        enableSystem={false}
        disableTransitionOnChange
      >
        <I18nProvider>
          <RouterProvider router={router} />
        </I18nProvider>
      </ThemeProvider>
    );
  } catch (error) {
    console.error('[Bootstrap] Root render failed', error);
    throw error;
  }
} else {
  console.error('[Bootstrap] Root element missing or already initialized', {
    hasRootElement: Boolean(rootElement),
    hasRootInnerHTML: Boolean(rootElement?.innerHTML),
  });
}
