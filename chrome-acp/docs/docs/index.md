---
pageType: home
hero:
  name: Siada Browser Add-on
  text: Browser Control for AI Agents
  tagline: chrome-acp brings your Siada CLI agent into the browser — chat with it and give it the power to see and interact with the pages you have open.
  actions:
    - theme: brand
      text: Quick Start
      link: /getting-started/quick-start
    - theme: alt
      text: Introduction
      link: /getting-started/introduction
features:
  - title: Works with Any ACP Agent
    details: siada-cli is the default agent; Claude Code, OpenCode, Gemini CLI, Codex CLI, and more also work.
    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/></svg>'
  - title: Managed by Siada CLI
    details: siada-browser setup / start / stop / restart / status, or the --browser-* flags on siada-cli.
    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="12" x="3" y="4" rx="2" ry="2"/><line x1="2" x2="22" y1="20" y2="20"/></svg>'
  - title: Operates as You
    details: Agents interact with pages using your real browser session.
    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>'
  - title: Browser Tools
    details: Read tabs, execute scripts, take screenshots, and interact with web pages.
    icon: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>'
---

chrome-acp is the browser add-on shipped with **Siada CLI** (the `chrome-acp/` directory of this repository). It is derived from the MIT-licensed **Chrome ACP** project and has been modified for Siada CLI — see [Attribution and license](/getting-started/introduction/#attribution-and-license).

No npm packages are published for this component: install it from this repository with `siada-browser setup <chrome-acp-dir>` (or `siada-cli --browser-setup <chrome-acp-dir>`), or from an explicit artifact host passed with `--base-url`.

