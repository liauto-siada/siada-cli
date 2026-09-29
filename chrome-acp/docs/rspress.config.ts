import { defineConfig } from '@rspress/core';

export default defineConfig({
  root: 'docs',
  base: '/chrome-acp/',
  title: 'Siada Browser Add-on (chrome-acp)',
  description: 'chrome-acp is the Siada CLI browser add-on: a Chrome extension plus a local proxy server that connect your browser to ACP agents such as siada-cli.',
  icon: '/favicon.png',
  logo: '/logo.png',
  // Enable llms.txt generation for AI/LLM consumption
  llms: true,
  themeConfig: {
    lastUpdated: true,
    editLink: {
      docRepoBaseUrl: 'https://github.com/liauto-siada/siada-cli/edit/main/chrome-acp/docs/docs',
      text: 'Edit this page on GitHub',
    },
    socialLinks: [
      {
        icon: 'github',
        mode: 'link',
        content: 'https://github.com/liauto-siada/siada-cli',
      },
    ],
    footer: {
      message: '© 2026 Siada CLI — chrome-acp browser add-on (MIT)',
    },
  },
  markdown: {
    showLineNumbers: true,
  },
});

