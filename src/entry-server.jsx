import React from 'react';
import { renderToString } from 'react-dom/server';
import { App } from './main.jsx';

export function renderPublicPage(initialData) {
  return renderToString(<App initialData={initialData} />);
}
