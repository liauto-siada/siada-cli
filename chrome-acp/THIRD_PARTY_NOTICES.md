# Third-Party Notices - chrome-acp browser add-on (Siada)

This file covers the third-party software that is redistributed with the
artifacts built from this directory:

* `packages/chrome-extension` - the MV3 Chrome extension, packed as
  `chrome-acp-extension-<version>.zip` by `just pack-extension`.
* `packages/proxy-server` - the local proxy (`acp-proxy`), packed as a tarball
  together with its production `node_modules` by `just pack-proxy`.
* `packages/web-client` - the PWA chat client; the `vite build` output is copied
  into `packages/proxy-server/public/` and served by the proxy.

## How the package sets and license data were determined

* **Extension + PWA (table in section 1, 243 packages)**: the `name@version`
  set is re-derived from the build metadata that the committed build tooling
  records for the current release build (`CHROME_ACP_BUILD_AUDIT=1`, written to
  the git-ignored `.build-audit/` directory): the top-level `inputs` keys in
  the Bun bundler metafile of the
  two extension bundles (`sidepanel`, `background`) plus the per-chunk module
  lists recorded for the PWA web-client build. Every listed path under
  `node_modules/` resolves to a package directory in the workspace
  `node_modules/.bun` install store, and each row's `name@version` is read from
  that directory's own `package.json`. The result is a **conservative input
  closure** - an upper bound, not an "all emitted" claim: a recorded input can
  still be partially tree-shaken, and the Bun metafile additionally lists
  modules that may not be emitted at all - and it is reproducible: re-running
  the release build with `CHROME_ACP_BUILD_AUDIT=1` in the environment and
  re-applying the same input extraction yields the same 243 rows, and
  re-checking the 243 rows against that metadata leaves no missing package
  (see the coverage note after the table in section 1). All 243 rows also
  appear as resolved entries of the committed `chrome-acp/bun.lock` and exist
  in `chrome-acp/node_modules/.bun` at exactly that version.
* **Predecessor source-map audit (kept as history)**: the table originally came
  from a predecessor build that emitted maps
  (`packages/chrome-extension/dist/**/*.js.map` and
  `packages/proxy-server/public/assets/*.js.map`), which referenced the resolved
  packages in the workspace `node_modules/.bun` store. The current release
  build does not emit source maps (`sourcemap: "none"` in
  `packages/chrome-extension/build.ts`, `sourcemap: false` in
  `packages/web-client/vite.config.ts`, and no `*.js.map` in the current `dist`
  trees), so that older audit cannot be repeated from the current artifacts.
  All 231 of its rows are still part of the current 243-row closure; the 12
  rows it did not list are reproduced with their full license texts in
  section 6.
* **Proxy (table in section 2)**: the production closure of the committed
  standalone npm lockfile `packages/proxy-server/package-lock.json`
  (lockfileVersion 3), installed into the tarball by
  `npm ci --omit=dev --ignore-scripts`: 92 production entries (78
  dependencies, 2 `peerDependencies` installed by `npm ci`, 12 platform
  optionals) and 5 `devDependencies` entries omitted. The previous revision of
  this file described the workspace `bun.lock` closure (77 packages); that
  table is kept in section 2 as previous build attributions.
* **License data**: each package's own `package.json` (`license`, `author`) and
  its `LICENSE`/`NOTICE` files. For the extension/PWA rows these are the
  packages as installed in `chrome-acp/node_modules/.bun/...` (the workspace's
  isolated install store); for the proxy
  rows they are the packages as installed by `npm ci` in the staged tarball
  (`release/chrome-acp-proxy-1.0.45/node_modules/` and inside the packed
  archive). License identifiers are the packages' own SPDX identifiers;
  copyright/attribution lines are quoted verbatim from the shipped license
  files.
* **Packages whose published npm tarball ships no LICENSE/NOTICE file** (7
  packages of the tables in sections 1-2): the license identifier is the one
  declared in the package's own `package.json`, and the absence of a license
  file was confirmed from the official registry tarball of that version (its
  tar member list contains no license file, and the tarball's
  `shasum`/`integrity` match the registry metadata). The copyright line quoted
  in the tables and the complete license text reproduced in section 6 come
  from a documented public source that is named for each package: the
  `## License` section of the package's own shipped `README.md`
  (`fastdom@1.0.12`); the upstream repository's root license file at the exact
  commit that the registry metadata records for the release (`gitHead`) for
  `rehype-katex@7.0.1`, `remark-math@6.0.0`, `@stricli/core@1.3.0` and
  `@stricli/auto-complete@1.3.0`; or - for `react-remove-scroll-bar@2.3.8` and
  `@hono/node-ws@1.3.1` - an upstream license file that the project added
  **after** the version was published. The after-the-fact files are **not**
  files of the published versions and are labelled as such in the tables and
  in section 6.

## 1. Bundled into the Chrome extension and the PWA web client

The table below is the 243-package input closure of the current build (method
note above; coverage note after the table). It is a superset of the earlier
231-row predecessor source-map audit: the 12 rows added from the current build
metadata are `radix-ui@1.6.7` and eleven `d3-*` modules (their full license
texts are in section 6).

| Package | Version | License | Copyright / attribution (verbatim from the package's LICENSE) |
|---|---|---|---|
| `@braintree/sanitize-url@7.1.2` | 7.1.2 | MIT | Copyright (c) 2017 Braintree |
| `@floating-ui/core@1.8.0` | 1.8.0 | MIT | Copyright (c) 2021-present Floating UI contributors |
| `@floating-ui/dom@1.8.0` | 1.8.0 | MIT | Copyright (c) 2021-present Floating UI contributors |
| `@floating-ui/react-dom@2.1.9` | 2.1.9 | MIT | Copyright (c) 2021-present Floating UI contributors |
| `@floating-ui/utils@0.2.12` | 0.2.12 | MIT | Copyright (c) 2021-present Floating UI contributors |
| `@iconify/utils@3.1.4` | 3.1.4 | MIT | Copyright (c) 2021-PRESENT Vjacheslav Trushkin |
| `@mermaid-js/parser@1.2.1` | 1.2.1 | MIT | Copyright (c) 2023 Yokozuna59 |
| `@radix-ui/number@1.1.3` | 1.1.3 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/primitive@1.1.7` | 1.1.7 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-arrow@1.1.15` | 1.1.15 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-collapsible@1.1.20` | 1.1.20 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-collection@1.1.15` | 1.1.15 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-compose-refs@1.1.5` | 1.1.5 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-context@1.2.2` | 1.2.2 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-dialog@1.1.23` | 1.1.23 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-direction@1.1.4` | 1.1.4 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-dismissable-layer@1.1.19` | 1.1.19 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-dropdown-menu@2.1.24` | 2.1.24 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-focus-guards@1.1.6` | 1.1.6 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-focus-scope@1.1.16` | 1.1.16 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-hover-card@1.1.23` | 1.1.23 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-id@1.1.4` | 1.1.4 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-label@2.1.15` | 2.1.15 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-menu@2.1.24` | 2.1.24 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-popover@1.1.23` | 1.1.23 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-popper@1.3.7` | 1.3.7 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-portal@1.1.17` | 1.1.17 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-presence@1.1.10` | 1.1.10 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-primitive@2.1.10` | 2.1.10 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-roving-focus@1.1.19` | 1.1.19 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-scroll-area@1.2.18` | 1.2.18 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-slot@1.3.3` | 1.3.3 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-tabs@1.1.21` | 1.1.21 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-tooltip@1.2.16` | 1.2.16 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-use-callback-ref@1.1.4` | 1.1.4 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-use-controllable-state@1.2.6` | 1.2.6 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-use-effect-event@0.0.5` | 0.0.5 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-use-is-hydrated@0.1.3` | 0.1.3 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-use-layout-effect@1.1.4` | 1.1.4 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-use-size@1.1.4` | 1.1.4 | MIT | Copyright (c) 2022 WorkOS |
| `@radix-ui/react-visually-hidden@1.2.11` | 1.2.11 | MIT | Copyright (c) 2022 WorkOS |
| `@shikijs/core@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `@shikijs/engine-javascript@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `@shikijs/engine-oniguruma@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `@shikijs/langs@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `@shikijs/themes@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `@shikijs/types@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `@shikijs/vscode-textmate@10.0.2` | 10.0.2 | MIT | Copyright (c) Microsoft Corporation |
| `@ungap/structured-clone@1.3.3` | 1.3.3 | ISC | Copyright (c) 2021, Andrea Giammarchi, @WebReflection |
| `@upsetjs/venn.js@2.0.0` | 2.0.0 | MIT | Copyright (c) 2013 Ben Frederickson<br>Copyright (c) 2021 Samuel Gratzl |
| `aria-hidden@1.2.6` | 1.2.6 | MIT | Copyright (c) 2017 Anton Korzunov |
| `bail@2.0.2` | 2.0.2 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `browser-image-compression@2.0.2` | 2.0.2 | MIT | Copyright (c) 2019 Donald Chan |
| `ccount@2.0.1` | 2.0.1 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `character-entities-html4@2.1.0` | 2.1.0 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `character-entities-legacy@3.0.0` | 3.0.0 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `class-variance-authority@0.7.1` | 0.7.1 | Apache-2.0 | Copyright 2022 Joe Bell |
| `clsx@2.1.1` | 2.1.1 | MIT | Copyright (c) Luke Edwards <luke.edwards05@gmail.com> (lukeed.com) |
| `cmdk@1.1.1` | 1.1.1 | MIT | Copyright (c) 2022 Paco Coursey |
| `comma-separated-tokens@2.0.3` | 2.0.3 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `cose-base@1.0.3` | 1.0.3 | MIT | Copyright (c) 2019 - present, iVis@Bilkent. |
| `cose-base@2.2.0` | 2.2.0 | MIT | Copyright (c) 2019 - present, iVis@Bilkent. |
| `cytoscape-cose-bilkent@4.1.0` | 4.1.0 | MIT | Copyright (c) 2016-2018, The Cytoscape Consortium. |
| `cytoscape-fcose@2.2.0` | 2.2.0 | MIT | Copyright (c) 2018 - present, iVis-at-Bilkent. |
| `cytoscape@3.34.1` | 3.34.1 | MIT | Copyright (c) 2016-2026, The Cytoscape Consortium. |
| `d3-array@2.12.1` | 2.12.1 | BSD-3-Clause | Copyright 2010-2020 Mike Bostock |
| `d3-array@3.2.4` | 3.2.4 | ISC | Copyright 2010-2023 Mike Bostock |
| `d3-axis@3.0.0` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-brush@3.0.0` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-chord@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-color@3.1.0` | 3.1.0 | ISC | Copyright 2010-2022 Mike Bostock |
| `d3-contour@4.0.2` | 4.0.2 | ISC | Copyright 2012-2023 Mike Bostock |
| `d3-delaunay@6.0.4` | 6.0.4 | ISC | Copyright 2018-2021 Observable, Inc.<br>Copyright 2021 Mapbox |
| `d3-dispatch@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-drag@3.0.0` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-dsv@3.0.1` | 3.0.1 | ISC | Copyright 2013-2021 Mike Bostock |
| `d3-ease@3.0.1` | 3.0.1 | BSD-3-Clause | Copyright 2010-2021 Mike Bostock<br>Copyright 2001 Robert Penner |
| `d3-fetch@3.0.1` | 3.0.1 | ISC | Copyright 2016-2021 Mike Bostock |
| `d3-force@3.0.0` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-format@3.1.2` | 3.1.2 | ISC | Copyright 2010-2026 Mike Bostock |
| `d3-geo@3.1.1` | 3.1.1 | ISC | Copyright 2010-2024 Mike Bostock<br>Copyright 2008-2012 Charles Karney |
| `d3-hierarchy@3.1.2` | 3.1.2 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-interpolate@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-path@1.0.9` | 1.0.9 | BSD-3-Clause | Copyright 2015-2016 Mike Bostock |
| `d3-path@3.1.0` | 3.1.0 | ISC | Copyright 2015-2022 Mike Bostock |
| `d3-polygon@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-quadtree@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-random@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-sankey@0.12.3` | 0.12.3 | BSD-3-Clause | Copyright 2015, Mike Bostock |
| `d3-scale-chromatic@3.1.0` | 3.1.0 | ISC | Copyright 2010-2024 Mike Bostock<br>Copyright 2002 Cynthia Brewer, Mark Harrower, and The Pennsylvania State University |
| `d3-scale@4.0.2` | 4.0.2 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-selection@3.0.0` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-shape@1.3.7` | 1.3.7 | BSD-3-Clause | Copyright 2010-2015 Mike Bostock |
| `d3-shape@3.2.0` | 3.2.0 | ISC | Copyright 2010-2022 Mike Bostock |
| `d3-time-format@4.1.0` | 4.1.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-time@3.1.0` | 3.1.0 | ISC | Copyright 2010-2022 Mike Bostock |
| `d3-timer@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-transition@3.0.1` | 3.0.1 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3-zoom@3.0.0` | 3.0.0 | ISC | Copyright 2010-2021 Mike Bostock |
| `d3@7.9.0` | 7.9.0 | ISC | Copyright 2010-2023 Mike Bostock |
| `dagre-d3-es@7.0.14` | 7.0.14 | MIT | Original dagre-d3 copyright: Copyright (c) 2013 Chris Pettitt<br>Original dagre copyright: Copyright (c) 2012-2014 Chris Pettitt<br>Original graphlib copyright: Copyright (c) 2012-2014 Chris Pettitt<br>Copyright (c) 2022-2024 Thibaut Lassalle, David Newell, Alois Klink, Sidharth Vinod and dagre-es contributors |
| `dayjs@1.11.23` | 1.11.23 | MIT | Copyright (c) 2018-present, iamkun |
| `decode-named-character-reference@1.3.0` | 1.3.0 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `devlop@1.1.0` | 1.1.0 | MIT | Copyright (c) 2023 Titus Wormer <tituswormer@gmail.com> |
| `dompurify@3.4.14` | 3.4.14 | Apache-2.0 *(dual-licensed; this option chosen)* | (c) Cure53 and other contributors *(from the source license header)*<br>*package.json author:* Dr.-Ing. Mario Heiderich, Cure53 <mario@cure53.de> (https://cure53.de/) |
| `entities@6.0.1` | 6.0.1 | BSD-2-Clause | Copyright (c) Felix Böhm |
| `es-toolkit@1.51.0` | 1.51.0 | MIT | Copyright (c) 2024 Viva Republica, Inc. |
| `escape-string-regexp@5.0.0` | 5.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `estree-util-is-identifier-name@3.0.0` | 3.0.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `extend@3.0.2` | 3.0.2 | MIT | Copyright (c) 2014 Stefan Thomas |
| `fastdom@1.0.12` | 1.0.12 | MIT | Copyright (c) 2016 Wilson Page <wilsonpage@me.com> *(the tarball ships no LICENSE file; quoted from the `## License` section of the package's own `README.md` - full text in section 6)* |
| `framer-motion@12.43.0` | 12.43.0 | MIT | Copyright (c) 2018 Framer B.V. |
| `get-east-asian-width@1.6.0` | 1.6.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `get-nonce@1.0.1` | 1.0.1 | MIT | Copyright (c) 2020 Anton Korzunov |
| `hast-util-from-dom@5.0.1` | 5.0.1 | ISC | Copyright (c) Keith McKnight <keith@mcknig.ht> |
| `hast-util-from-html-isomorphic@2.0.0` | 2.0.0 | MIT | Copyright (c) 2023 Remco Haszing <remcohaszing@gmail.com> |
| `hast-util-from-parse5@8.0.3` | 8.0.3 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `hast-util-is-element@3.0.0` | 3.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `hast-util-parse-selector@4.0.0` | 4.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `hast-util-raw@9.1.0` | 9.1.0 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `hast-util-sanitize@5.0.2` | 5.0.2 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `hast-util-to-html@9.0.5` | 9.0.5 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `hast-util-to-jsx-runtime@2.3.6` | 2.3.6 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `hast-util-to-parse5@8.0.1` | 8.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `hast-util-to-text@4.0.2` | 4.0.2 | MIT | Copyright (c) 2019 Titus Wormer <tituswormer@gmail.com> |
| `hast-util-whitespace@3.0.0` | 3.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `hastscript@9.0.1` | 9.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `html-void-elements@3.0.0` | 3.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `inline-style-parser@0.2.7` | 0.2.7 | MIT | Copyright (c) 2012 TJ Holowaychuk <tj@vision-media.ca> |
| `internmap@1.0.1` | 1.0.1 | ISC | Copyright 2021 Mike Bostock |
| `is-plain-obj@4.1.0` | 4.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `katex@0.16.47` | 0.16.47 | MIT | Copyright (c) 2013-2020 Khan Academy and other contributors |
| `khroma@2.1.0` | 2.1.0 | MIT | Copyright (c) 2019-present Fabio Spampinato, Andrew Maney |
| `layout-base@1.0.2` | 1.0.2 | MIT | Copyright (c) 2019 iVis@Bilkent |
| `layout-base@2.0.1` | 2.0.1 | MIT | Copyright (c) 2019 iVis@Bilkent |
| `lodash-es@4.18.1` | 4.18.1 | MIT | Copyright OpenJS Foundation and other contributors <https://openjsf.org/><br>Copyright and related rights for sample code are waived via CC0. Sample |
| `longest-streak@3.1.0` | 3.1.0 | MIT | Copyright (c) 2015 Titus Wormer <mailto:tituswormer@gmail.com> |
| `lucide-react@0.542.0` | 0.542.0 | ISC | Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.<br>Copyright (c) 2013-2023 Cole Bemis |
| `lucide-react@0.555.0` | 0.555.0 | ISC | Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.<br>Copyright (c) 2013-2023 Cole Bemis |
| `markdown-table@3.0.4` | 3.0.4 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `marked@16.4.2` | 16.4.2 | MIT | Copyright (c) 2018+, MarkedJS (https://github.com/markedjs/)<br>Copyright (c) 2011-2018, Christopher Jeffrey (https://github.com/chjj/)<br>Copyright © 2004, John Gruber |
| `mdast-util-find-and-replace@3.0.2` | 3.0.2 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-from-markdown@2.0.3` | 2.0.3 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-gfm-autolink-literal@2.0.1` | 2.0.1 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-gfm-footnote@2.1.0` | 2.1.0 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-gfm-strikethrough@2.0.0` | 2.0.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-gfm-table@2.0.0` | 2.0.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-gfm-task-list-item@2.0.0` | 2.0.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-gfm@3.1.0` | 3.1.0 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-math@3.0.0` | 3.0.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-phrasing@4.1.0` | 4.1.0 | MIT | Copyright (c) 2017 Titus Wormer <tituswormer@gmail.com><br>Copyright (c) 2017 Victor Felder <victor@draft.li> |
| `mdast-util-to-hast@13.2.1` | 13.2.1 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-to-markdown@2.1.2` | 2.1.2 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `mdast-util-to-string@4.0.0` | 4.0.0 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `mermaid@11.17.0` | 11.17.0 | MIT | Copyright (c) 2014 - 2022 Knut Sveidqvist |
| `micromark-core-commonmark@2.0.3` | 2.0.3 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-cjk-friendly-gfm-strikethrough@1.2.3` | 1.2.3 | MIT | Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp><br>Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-cjk-friendly-util@2.1.1` | 2.1.1 | MIT | Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp><br>Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-cjk-friendly@1.2.3` | 1.2.3 | MIT | Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp><br>Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-gfm-autolink-literal@2.1.0` | 2.1.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-gfm-footnote@2.1.0` | 2.1.0 | MIT | Copyright (c) 2021 Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-gfm-strikethrough@2.1.0` | 2.1.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-gfm-table@2.1.1` | 2.1.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-gfm-task-list-item@2.1.0` | 2.1.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-gfm@3.0.0` | 3.0.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `micromark-extension-math@3.1.0` | 3.1.0 | MIT | Copyright (c) 2020 Titus Wormer <tituswormer@gmail.com> |
| `micromark-factory-destination@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-factory-label@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-factory-space@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-factory-title@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-factory-whitespace@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-character@2.1.1` | 2.1.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-chunked@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-classify-character@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-combine-extensions@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-decode-numeric-character-reference@2.0.2` | 2.0.2 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-decode-string@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-html-tag-name@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-normalize-identifier@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-resolve-all@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-sanitize-uri@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-subtokenize@2.1.0` | 2.1.0 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark-util-symbol@2.0.1` | 2.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `micromark@4.0.2` | 4.0.2 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `motion-dom@12.43.0` | 12.43.0 | MIT | Copyright (c) 2024 [Motion](https://motion.dev) B.V. |
| `motion-utils@12.39.0` | 12.39.0 | MIT | Copyright (c) 2024 [Motion](https://motion.dev) B.V. |
| `motion@12.43.0` | 12.43.0 | MIT | Copyright (c) 2024 [Motion](https://motion.dev) B.V. |
| `nanoid@5.1.16` | 5.1.16 | MIT | Copyright 2017 Andrey Sitnik <andrey@sitnik.es> |
| `oniguruma-parser@0.12.2` | 0.12.2 | MIT | Copyright (c) 2025-2026 Steven Levithan |
| `oniguruma-to-es@4.3.6` | 4.3.6 | MIT | Copyright (c) 2024-2026 Steven Levithan |
| `parse5@7.3.0` | 7.3.0 | MIT | Copyright (c) 2013-2019 Ivan Nikulin (ifaaan@gmail.com, https://github.com/inikulin) |
| `property-information@7.2.0` | 7.2.0 | MIT | Copyright (c) Titus Wormer <mailto:tituswormer@gmail.com> |
| `qr-scanner@1.4.2` | 1.4.2 | MIT | Copyright (c) 2017 Nimiq, danimoh |
| `radix-ui@1.6.7` | 1.6.7 | MIT | Copyright (c) 2022 WorkOS |
| `react-dom@19.2.8` | 19.2.8 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `react-remove-scroll-bar@2.3.8` | 2.3.8 | MIT | Copyright (c) 2025 Anton Korzunov <thekashey@gmail.com> *(the tarball ships no LICENSE file; this is an upstream `LICENSE` added after the release - not a file of the published version; full text in section 6)* |
| `react-remove-scroll@2.7.2` | 2.7.2 | MIT | Copyright (c) 2017 Anton Korzunov |
| `react-style-singleton@2.2.3` | 2.2.3 | MIT | Copyright (c) 2017 Anton Korzunov |
| `react@19.2.8` | 19.2.8 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `regex-recursion@6.0.2` | 6.0.2 | MIT | Copyright (c) 2025 Steven Levithan |
| `regex-utilities@2.3.0` | 2.3.0 | MIT | Copyright (c) 2024 Steven Levithan |
| `regex@6.1.0` | 6.1.0 | MIT | Copyright (c) 2025 Steven Levithan |
| `rehype-harden@1.1.8` | 1.1.8 | MIT | Copyright (c) 2025 Vercel Inc. |
| `rehype-katex@7.0.1` | 7.0.1 | MIT | Copyright (c) 2017 Junyoung Choi <fluke8259@gmail.com> *(the tarball ships no LICENSE file; from the repository-root `license` file at the release's `gitHead` commit - full text in section 6)* |
| `rehype-raw@7.0.0` | 7.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `rehype-sanitize@6.0.0` | 6.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `remark-cjk-friendly-gfm-strikethrough@1.2.3` | 1.2.3 | MIT | Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp><br>Based on remark-gfm:<br>Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `remark-cjk-friendly@1.2.3` | 1.2.3 | MIT | Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp><br>Based on remark-gfm:<br>Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `remark-gfm@4.0.1` | 4.0.1 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `remark-math@6.0.0` | 6.0.0 | MIT | Copyright (c) 2017 Junyoung Choi <fluke8259@gmail.com> *(the tarball ships no LICENSE file; from the repository-root `license` file at the release's `gitHead` commit - full text in section 6)* |
| `remark-parse@11.0.0` | 11.0.0 | MIT | Copyright (c) 2014 Titus Wormer <tituswormer@gmail.com> |
| `remark-rehype@11.1.2` | 11.1.2 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `remend@1.0.1` | 1.0.1 | Apache-2.0 | Copyright 2023 Vercel, Inc. |
| `roughjs@4.6.6` | 4.6.6 | MIT | Copyright (c) 2019 Preet Shihn |
| `scheduler@0.27.0` | 0.27.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `shiki@3.23.0` | 3.23.0 | MIT | Copyright (c) 2021 Pine Wu<br>Copyright (c) 2023 Anthony Fu <https://github.com/antfu> |
| `space-separated-tokens@2.0.2` | 2.0.2 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `streamdown@1.6.11` | 1.6.11 | Apache-2.0 | Copyright 2023 Vercel, Inc. |
| `stringify-entities@4.0.4` | 4.0.4 | MIT | Copyright (c) 2015 Titus Wormer <mailto:tituswormer@gmail.com> |
| `style-to-js@1.1.21` | 1.1.21 | MIT | Copyright (c) 2020 Menglin "Mark" Xu <mark@remarkablemark.org> |
| `style-to-object@1.0.14` | 1.0.14 | MIT | Copyright (c) 2017 Menglin "Mark" Xu <mark@remarkablemark.org> |
| `stylis@4.4.0` | 4.4.0 | MIT | Copyright (c) 2016-present Sultan Tarimo |
| `tailwind-merge@3.6.0` | 3.6.0 | MIT | Copyright (c) 2021 Dany Castillo |
| `trim-lines@3.0.1` | 3.0.1 | MIT | Copyright (c) 2015 Titus Wormer <mailto:tituswormer@gmail.com> |
| `trough@2.2.0` | 2.2.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `ts-dedent@2.3.0` | 2.3.0 | MIT | Copyright (c) 2018 Tamino Martinius |
| `tslib@2.8.1` | 2.8.1 | 0BSD | Copyright (c) Microsoft Corporation. |
| `unified@11.0.5` | 11.0.5 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `unist-util-find-after@5.0.0` | 5.0.0 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `unist-util-is@6.0.1` | 6.0.1 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `unist-util-position@5.0.0` | 5.0.0 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `unist-util-stringify-position@4.0.0` | 4.0.0 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `unist-util-visit-parents@6.0.2` | 6.0.2 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `unist-util-visit@5.1.0` | 5.1.0 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `use-callback-ref@1.3.3` | 1.3.3 | MIT | Copyright (c) 2017 Anton Korzunov |
| `use-sidecar@1.1.3` | 1.1.3 | MIT | Copyright (c) 2017 Anton Korzunov |
| `use-stick-to-bottom@1.1.6` | 1.1.6 | MIT | Copyright (c) 2024 - present StackBlitz |
| `uuid@14.0.2` | 14.0.2 | MIT | Copyright (c) 2010-2020 Robert Kieffer and other contributors |
| `vfile-location@5.0.3` | 5.0.3 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `vfile-message@4.0.3` | 4.0.3 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `vfile@6.0.3` | 6.0.3 | MIT | Copyright (c) 2015 Titus Wormer <tituswormer@gmail.com> |
| `web-namespaces@2.0.1` | 2.0.1 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |
| `zwitch@2.0.4` | 2.0.4 | MIT | Copyright (c) 2016 Titus Wormer <tituswormer@gmail.com> |

**Coverage note (current bundles).** Re-checking the metafile `inputs` keys
and the PWA chunk module lists against the 243 rows above leaves no missing
package: the two extension bundles
(`sidepanel`, `background`) together record 243 distinct `name@version` inputs
and the PWA web-client chunks record 231 of them, and every one appears in the
table (`missing = []`). The 12 extension-only rows - `radix-ui@1.6.7` and the
eleven `d3-*` modules - are the ones added from the current metadata; their
full license files are reproduced in section 6. The closure is conservative
rather than an emitted-modules claim: the current release build emits no source
maps, so a listed input can in principle still be partially tree-shaken or
dropped from the output. The five declared-but-tree-shaken packages are listed
in section 4.

## 2. Redistributed with the proxy tarball (`node_modules` installed by `npm ci`)

`just pack-proxy` builds the tarball from the committed standalone npm
lockfile `packages/proxy-server/package-lock.json` (lockfileVersion 3): it
copies `dist/`, `public/`, `package.json`, `package-lock.json`, `LICENSE`
and this file into a clean staging directory and runs
`npm ci --omit=dev --ignore-scripts` there. `npm ci` installs the lockfile's
production closure from the npm registry into a real (non-symlink)
`node_modules`; the workspace `bun.lock` / `node_modules/.bun` store is not
copied.

The lockfile records 98 package entries: 92 production entries — 78 regular
dependencies, 2 `peerDependencies` installed by `npm ci` (`typescript`,
`zod`) and 12 platform optionals (the `@parcel/watcher-<os>-<arch>` native
bindings) — plus 5 `devDependencies` entries and the root entry, which
`--omit=dev` excludes. All 92 production entries are listed below. A tarball
packed on a given platform contains the 80 non-optional entries plus the one
`@parcel/watcher-<os>-<arch>` variant for that platform (81 install entries);
`chrome-acp-proxy-1.0.45.tar.gz` was packed on darwin-arm64 and therefore
contains `@parcel/watcher-darwin-arm64`. `tslib` appears twice: 2.8.1 at the
top level and 1.14.1 nested under `tsyringe/node_modules/`. The eleven
`@parcel/watcher-<os>-<arch>` variants that are not installed on the packing
platform are listed from the lockfile (name, version, license identifier) with
the package-family LICENSE attribution, the same text as the installed
`@parcel/watcher` and `@parcel/watcher-darwin-arm64` copies.

| Package | Version | License | Copyright / attribution (verbatim from the package's LICENSE) |
|---|---|---|---|
| `@agentclientprotocol/sdk` | 0.14.1 | Apache-2.0 | Copyright 2025 Zed Industries, Inc. and contributors |
| `@hono/node-server` | 1.19.17 | MIT | Copyright (c) 2022 - present, Yusuke Wada and Hono contributors |
| `@hono/node-ws` | 1.3.1 | MIT | Copyright (c) 2022 - present, Yusuke Wada and Hono contributors *(the tarball ships no LICENSE file; this is an upstream `LICENSE` added after the release - not a file of the published version; full text in section 6)* |
| `@noble/hashes` | 1.8.0 | MIT | Copyright (c) 2022 Paul Miller (https://paulmillr.com) |
| `@parcel/watcher-android-arm64` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-darwin-arm64` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-darwin-x64` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-freebsd-x64` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-linux-arm-glibc` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-linux-arm-musl` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-linux-arm64-glibc` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-linux-arm64-musl` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-linux-x64-glibc` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-linux-x64-musl` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-win32-arm64` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher-win32-x64` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@parcel/watcher` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@peculiar/asn1-cms` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-csr` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-ecc` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-pfx` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-pkcs8` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-pkcs9` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-rsa` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-schema` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-x509-attr` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-x509` | 2.10.0 | MIT | Copyright (c) 2020 |
| `@peculiar/utils` | 2.0.3 | MIT | Copyright (c) 2017-2026 Peculiar Ventures, LLC |
| `@peculiar/x509` | 1.14.3 | MIT | Copyright (c) Peculiar Ventures. All rights reserved. |
| `@pinojs/redact` | 0.4.0 | MIT | Copyright (c) 2025 pinojs contributors |
| `@stricli/auto-complete` | 1.3.0 | Apache-2.0 | Copyright 2024 Bloomberg Finance L.P. *(the tarball ships no LICENSE file; from the repository-root `LICENSE` file at the release's `gitHead` commit - full text in section 6)* |
| `@stricli/core` | 1.3.0 | Apache-2.0 | Copyright 2024 Bloomberg Finance L.P. *(the tarball ships no LICENSE file; from the repository-root `LICENSE` file at the release's `gitHead` commit - full text in section 6)* |
| `ansi-regex` | 5.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `ansi-styles` | 4.3.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `asn1js` | 3.0.10 | BSD-3-Clause | Copyright (c) 2014, GMO GlobalSign<br>Copyright (c) 2015-2022, Peculiar Ventures<br>Author 2014-2019, Yury Strozhevsky |
| `atomic-sleep` | 1.0.0 | MIT | Copyright (c) 2020 David Mark Clements |
| `bytestreamjs` | 2.0.1 | BSD-3-Clause | Copyright (c) 2016-2022, Peculiar Ventures<br>Author 2016-2019, Yury Strozhevsky |
| `camelcase` | 5.3.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `cliui` | 6.0.0 | ISC | Copyright (c) 2015, Contributors |
| `color-convert` | 2.0.1 | MIT | Copyright (c) 2011-2016 Heather Arthur <fayearthur@gmail.com> |
| `color-name` | 1.1.4 | MIT | Copyright (c) 2015 Dmitry Ivanov |
| `decamelize` | 1.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `detect-libc` | 2.1.2 | Apache-2.0 | *package.json author:* Lovell Fuller <npm@lovell.info> |
| `dijkstrajs` | 1.0.3 | MIT | Copyright (C) 2008 |
| `emoji-regex` | 8.0.0 | MIT | Copyright Mathias Bynens <https://mathiasbynens.be/> |
| `find-up` | 4.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `get-caller-file` | 2.0.5 | ISC | Copyright 2018 Stefan Penner |
| `hono` | 4.13.13 | MIT | Copyright (c) 2021 - present, Yusuke Wada and Hono contributors |
| `is-extglob` | 2.1.1 | MIT | Copyright (c) 2014-2016, Jon Schlinkert |
| `is-fullwidth-code-point` | 3.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `is-glob` | 4.0.3 | MIT | Copyright (c) 2014-2017, Jon Schlinkert. |
| `locate-path` | 5.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `node-addon-api` | 7.1.1 | MIT | Copyright (c) 2017 [Node.js API collaborators](https://github.com/nodejs/node-addon-api#collaborators) |
| `on-exit-leak-free` | 2.1.2 | MIT | Copyright (c) 2021 Matteo Collina |
| `p-limit` | 2.3.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `p-locate` | 4.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `p-try` | 2.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `path-exists` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `picomatch` | 4.0.7 | MIT | Copyright (c) 2017-present, Jon Schlinkert. |
| `pino-abstract-transport` | 3.0.0 | MIT | Copyright (c) 2021 pino |
| `pino-std-serializers` | 7.1.0 | MIT | Copyright Mateo Collina, David Mark Clements, James Sumners |
| `pino` | 10.4.0 | MIT | Copyright (c) 2016-present Matteo Collina, David Mark Clements and the Pino contributors listed at <https://github.com/pinojs/pino#the-team> and in the README file. |
| `pkijs` | 3.4.1 | BSD-3-Clause | Copyright (c) 2014, GlobalSign<br>Copyright (c) 2015-2019, Peculiar Ventures<br>Author 2014-2019, Yury Strozhevsky |
| `pngjs` | 5.0.0 | MIT | pngjs2 original work Copyright (c) 2015 Luke Page & Original Contributors<br>pngjs derived work Copyright (c) 2012 Kuba Niegowski |
| `process-warning` | 5.1.0 | MIT | Copyright (c) 2020-present The Fastify team <https://github.com/fastify/fastify#team> |
| `pvtsutils` | 1.3.6 | MIT | Copyright (c) 2017-2024 Peculiar Ventures, LLC |
| `pvutils` | 1.2.0 | MIT | Copyright (c) 2016-2019, Peculiar Ventures<br>Author 2016-2019, Yury Strozhevsky |
| `qrcode` | 1.5.4 | MIT | Copyright (c) 2012 Ryan Day |
| `quick-format-unescaped` | 4.0.4 | MIT | Copyright (c) 2016-2019 David Mark Clements |
| `real-require` | 1.0.0 | MIT | Copyright (c) 2021 Paolo Insogna and the real-require contributors |
| `reflect-metadata` | 0.2.2 | Apache-2.0 | *package.json author:* Ron Buckton <ron.buckton@microsoft.com> |
| `require-directory` | 2.1.1 | MIT | Copyright (c) 2011 Troy Goode <troygoode@gmail.com> |
| `require-main-filename` | 2.0.0 | ISC | Copyright (c) 2016, Contributors |
| `safe-stable-stringify` | 2.5.0 | MIT | Copyright (c) Ruben Bridgewater |
| `selfsigned` | 5.5.0 | MIT | Copyright (c) 2013 José F. Romaniello |
| `set-blocking` | 2.0.0 | ISC | Copyright (c) 2016, Contributors |
| `sonic-boom` | 4.2.1 | MIT | Copyright (c) 2017 Matteo Collina |
| `split2` | 4.2.0 | ISC | Copyright (c) 2014-2018, Matteo Collina <hello@matteocollina.com> |
| `string-width` | 4.2.3 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `strip-ansi` | 6.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `thread-stream` | 4.2.0 | MIT | Copyright (c) 2021 Matteo Collina |
| `tslib` | 1.14.1 | 0BSD | Copyright (c) Microsoft Corporation. |
| `tslib` | 2.8.1 | 0BSD | Copyright (c) Microsoft Corporation. |
| `tsyringe` | 4.10.0 | MIT | Copyright (c) Microsoft Corporation. All rights reserved. |
| `typescript` | 5.9.3 | Apache-2.0 | *package.json author:* Microsoft Corp. — see `ThirdPartyNoticeText.txt` in section 6 |
| `which-module` | 2.0.1 | ISC | Copyright (c) 2016, Contributors |
| `wrap-ansi` | 6.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `ws` | 8.22.0 | MIT | Copyright (c) 2011 Einar Otto Stangvik <einaros@gmail.com><br>Copyright (c) 2013 Arnout Kazemier and contributors<br>Copyright (c) 2016 Luigi Pinca and contributors |
| `y18n` | 4.0.3 | ISC | Copyright (c) 2015, Contributors |
| `yargs-parser` | 18.1.3 | ISC | Copyright (c) 2016, Contributors |
| `yargs` | 15.4.1 | MIT | Copyright 2010 James Halliday (mail@substack.net); Modified work Copyright 2014 Contributors (ben@npmjs.com) |
| `zod` | 4.6.5 | MIT | Copyright (c) 2025 Colin McDonnell |

### Previous build attributions: the earlier `bun.lock` closure (77 packages)

The previous revision of this file derived the proxy table from the workspace
lockfile `chrome-acp/bun.lock` (a 77-package production closure). That closure
is a superset of the current one at package-name level (it contains no package
name that the npm lockfile lacks), but it does not describe the package set
`npm ci` actually installs: it has no entry for `typescript`, `zod` or the
platform optionals, and 17 names resolve to versions other than the ones this
table lists (`tslib` also gains a second, nested 1.14.1 copy). It is retained
below as previous build attributions (over-inclusive for the current
artifact); the authoritative list of what the tarball redistributes is the
table above.

| Package | Version | License | Copyright / attribution (verbatim from the package's LICENSE) |
|---|---|---|---|
| `@agentclientprotocol/sdk` | 0.14.1 | Apache-2.0 | Copyright 2025 Zed Industries, Inc. and contributors |
| `@hono/node-server` | 1.19.17 | MIT | Copyright (c) 2022 - present, Yusuke Wada and Hono contributors |
| `@hono/node-ws` | 1.3.1 | MIT | Copyright (c) 2022 - present, Yusuke Wada and Hono contributors *(no LICENSE file in the published tarball; upstream `LICENSE` added after the release)* |
| `@noble/hashes` | 1.4.0 | MIT | Copyright (c) 2022 Paul Miller (https://paulmillr.com) |
| `@parcel/watcher` | 2.6.0 | MIT | Copyright (c) 2017-present Devon Govett |
| `@peculiar/asn1-cms` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-csr` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-ecc` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-pfx` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-pkcs8` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-pkcs9` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-rsa` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-schema` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-x509` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/asn1-x509-attr` | 2.9.4 | MIT | Copyright (c) 2020 |
| `@peculiar/utils` | 2.0.3 | MIT | Copyright (c) 2017-2026 Peculiar Ventures, LLC |
| `@peculiar/x509` | 1.14.3 | MIT | *package.json author:* Peculiar Ventures LLC |
| `@pinojs/redact` | 0.4.0 | MIT | Copyright (c) 2025 pinojs contributors |
| `@stricli/auto-complete` | 1.3.0 | Apache-2.0 | Copyright 2024 Bloomberg Finance L.P. *(repository-root `LICENSE` at the release's `gitHead`; no LICENSE in the published tarball)* |
| `@stricli/core` | 1.3.0 | Apache-2.0 | Copyright 2024 Bloomberg Finance L.P. *(repository-root `LICENSE` at the release's `gitHead`; no LICENSE in the published tarball)* |
| `ansi-regex` | 5.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `ansi-styles` | 4.3.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `asn1js` | 3.0.10 | BSD-3-Clause | Copyright (c) 2014, GMO GlobalSign<br>Copyright (c) 2015-2022, Peculiar Ventures |
| `atomic-sleep` | 1.0.0 | MIT | Copyright (c) 2020 David Mark Clements |
| `bytestreamjs` | 2.0.1 | BSD-3-Clause | Copyright (c) 2016-2022, Peculiar Ventures |
| `camelcase` | 5.3.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `cliui` | 6.0.0 | ISC | Copyright (c) 2015, Contributors |
| `color-convert` | 2.0.1 | MIT | Copyright (c) 2011-2016 Heather Arthur <fayearthur@gmail.com> |
| `color-name` | 1.1.4 | MIT | Copyright (c) 2015 Dmitry Ivanov |
| `decamelize` | 1.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `detect-libc` | 2.1.2 | Apache-2.0 | *package.json author:* Lovell Fuller <npm@lovell.info> |
| `dijkstrajs` | 1.0.3 | MIT | Copyright (C) 2008 |
| `emoji-regex` | 8.0.0 | MIT | Copyright Mathias Bynens <https://mathiasbynens.be/> |
| `find-up` | 4.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `get-caller-file` | 2.0.5 | ISC | Copyright 2018 Stefan Penner |
| `hono` | 4.13.3 | MIT | Copyright (c) 2021 - present, Yusuke Wada and Hono contributors |
| `is-extglob` | 2.1.1 | MIT | Copyright (c) 2014-2016, Jon Schlinkert |
| `is-fullwidth-code-point` | 3.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `is-glob` | 4.0.3 | MIT | Copyright (c) 2014-2017, Jon Schlinkert. |
| `locate-path` | 5.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `node-addon-api` | 7.1.1 | MIT | Copyright (c) 2017 [Node.js API collaborators](https://github.com/nodejs/node-addon-api#collaborators) |
| `on-exit-leak-free` | 2.1.2 | MIT | Copyright (c) 2021 Matteo Collina |
| `p-limit` | 2.3.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `p-locate` | 4.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `p-try` | 2.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `path-exists` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `picomatch` | 4.0.5 | MIT | Copyright (c) 2017-present, Jon Schlinkert. |
| `pino` | 10.3.1 | MIT | Copyright (c) 2016-2025 Matteo Collina, David Mark Clements and the Pino contributors listed at <https://github.com/pinojs/pino#the-team> and in the README file. |
| `pino-abstract-transport` | 3.0.0 | MIT | Copyright (c) 2021 pino |
| `pino-std-serializers` | 7.1.0 | MIT | Copyright Mateo Collina, David Mark Clements, James Sumners |
| `pkijs` | 3.4.0 | BSD-3-Clause | Copyright (c) 2014, GlobalSign<br>Copyright (c) 2015-2019, Peculiar Ventures |
| `pngjs` | 5.0.0 | MIT | pngjs2 original work Copyright (c) 2015 Luke Page & Original Contributors<br>pngjs derived work Copyright (c) 2012 Kuba Niegowski |
| `process-warning` | 5.1.0 | MIT | Copyright (c) 2020-present The Fastify team <https://github.com/fastify/fastify#team> |
| `pvtsutils` | 1.3.6 | MIT | Copyright (c) 2017-2024 Peculiar Ventures, LLC |
| `pvutils` | 1.2.0 | MIT | Copyright (c) 2016-2019, Peculiar Ventures |
| `qrcode` | 1.5.4 | MIT | Copyright (c) 2012 Ryan Day |
| `quick-format-unescaped` | 4.0.4 | MIT | Copyright (c) 2016-2019 David Mark Clements |
| `real-require` | 0.2.0 | MIT | Copyright (c) 2021 Paolo Insogna and the real-require contributors |
| `reflect-metadata` | 0.2.2 | Apache-2.0 | *package.json author:* Ron Buckton <ron.buckton@microsoft.com> |
| `require-directory` | 2.1.1 | MIT | Copyright (c) 2011 Troy Goode <troygoode@gmail.com> |
| `require-main-filename` | 2.0.0 | ISC | Copyright (c) 2016, Contributors |
| `safe-stable-stringify` | 2.5.0 | MIT | Copyright (c) Ruben Bridgewater |
| `selfsigned` | 5.5.0 | MIT | Copyright (c) 2013 José F. Romaniello |
| `set-blocking` | 2.0.0 | ISC | Copyright (c) 2016, Contributors |
| `sonic-boom` | 4.2.1 | MIT | Copyright (c) 2017 Matteo Collina |
| `split2` | 4.2.0 | ISC | Copyright (c) 2014-2018, Matteo Collina <hello@matteocollina.com> |
| `string-width` | 4.2.3 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `strip-ansi` | 6.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `thread-stream` | 4.2.0 | MIT | Copyright (c) 2021 Matteo Collina |
| `tslib` | 2.8.1 | 0BSD | Copyright (c) Microsoft Corporation. |
| `tsyringe` | 4.10.0 | MIT | *package.json author:* Steven Hobson-Campbell |
| `which-module` | 2.0.1 | ISC | Copyright (c) 2016, Contributors |
| `wrap-ansi` | 6.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `ws` | 8.21.3 | MIT | Copyright (c) 2011 Einar Otto Stangvik <einaros@gmail.com><br>Copyright (c) 2013 Arnout Kazemier and contributors<br>Copyright (c) 2016 Luigi Pinca and contributors |
| `y18n` | 4.0.3 | ISC | Copyright (c) 2015, Contributors |
| `yargs` | 15.4.1 | MIT | Copyright 2010 James Halliday (mail@substack.net); Modified work Copyright 2014 Contributors (ben@npmjs.com) |
| `yargs-parser` | 18.1.3 | ISC | Copyright (c) 2016, Contributors |

## 3. Vendored component: Mozilla pdf.js

* **pdf.js 6.3.289 (generic viewer build)** - Apache License 2.0 - Mozilla
  Foundation. Vendored by `packages/chrome-extension/scripts/vendor-pdf-viewer.ts`
  from the official `pdfjs-6.3.289-dist.zip` release archive into
  `vendor/pdf/` (the archive's LICENSE is kept at `vendor/pdf/LICENSE`) and
  copied to `dist/pdf/` by the extension build, so the extension zip contains
  the license at `dist/pdf/LICENSE`. The upstream distribution is
  redistributed unmodified.

## 4. Declared dependencies that the current build does not bundle

These packages are imported by extension/shared source files
(`ai-elements/canvas.tsx`, `ui/carousel.tsx`, `ai-elements/context.tsx`) but
were tree-shaken out of the bundles in the predecessor source-map audit, and
they are absent from the recorded input closure of the current build as well
(see the method note above). All five remain declared dependencies and are
present in the current workspace resolution (`chrome-acp/bun.lock` and
`node_modules/.bun`). They are listed so that the notice stays correct if a
later build includes them.

| Package | Version | License | Copyright / attribution |
|---|---|---|---|
| `@xyflow/react` | 12.11.3 | MIT | Copyright (c) 2019-2025 webkid GmbH |
| `embla-carousel-react` | 8.6.0 | MIT | Copyright (c) David Jerleke *(upstream repository LICENSE; the published tarballs contain no LICENSE file)* |
| `embla-carousel` | 8.6.0 | MIT | Copyright (c) David Jerleke *(upstream repository LICENSE; the published tarballs contain no LICENSE file)* |
| `embla-carousel-reactive-utils` | 8.6.0 | MIT | Copyright (c) David Jerleke *(upstream repository LICENSE; the published tarballs contain no LICENSE file)* |
| `tokenlens` | 1.3.1 | MIT | Copyright (c) [2025] [Nicklas Scharpff] |

## 5. License texts

### MIT

The text below is reproduced from `@braintree/sanitize-url@7.1.2` (`LICENSE`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
MIT License

Copyright (c) 2017 Braintree

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### ISC

The text below is reproduced from `d3-array@3.2.4` (`LICENSE`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
Copyright 2010-2023 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### BSD-2-Clause

The text below is reproduced from `entities@6.0.1` (`LICENSE`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
Copyright (c) Felix Böhm
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS,
EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### BSD-3-Clause

The text below is reproduced from `d3-array@2.12.1` (`LICENSE`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
Copyright 2010-2020 Mike Bostock
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the author nor the names of contributors may be used to
  endorse or promote products derived from this software without specific prior
  written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### 0BSD

The text below is reproduced from `tslib` (`LICENSE.txt`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```

### Apache-2.0

The text below is reproduced from `dompurify@3.4.14` (`LICENSE`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```


## 6. Additional license texts

LICENSE files that carry extra attribution text beyond the license body (and
the one upstream NOTICE file) are reproduced in full. For the packages added by
the current build's input closure (section 1), the complete shipped `LICENSE`
file is reproduced as well, so each of those `name@version` rows can be
compared verbatim against its upstream file. For the packages whose published
tarball contains no license file, the complete text is reproduced from the
public source that is named in that subsection:

### `cytoscape@3.34.1` (`LICENSE`)

```
Copyright (c) 2016-2026, The Cytoscape Consortium.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the “Software”), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `d3-scale-chromatic@3.1.0` (`LICENSE`)

```
Copyright 2010-2024 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.

Apache-Style Software License for ColorBrewer software and ColorBrewer Color Schemes

Copyright 2002 Cynthia Brewer, Mark Harrower, and The Pennsylvania State University

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
```

### `d3-chord@3.0.1` (`LICENSE`) — identical file also shipped by: `d3-chord@3.0.1`, `d3-drag@3.0.0`, `d3-force@3.0.0`, `d3-polygon@3.0.1`, `d3-quadtree@3.0.1`, `d3-random@3.0.1`

```
Copyright 2010-2021 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### `d3-contour@4.0.2` (`LICENSE`)

```
Copyright 2012-2023 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### `d3-delaunay@6.0.4` (`LICENSE`)

```
Copyright 2018-2021 Observable, Inc.
Copyright 2021 Mapbox

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### `d3-dsv@3.0.1` (`LICENSE`)

```
Copyright 2013-2021 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### `d3-fetch@3.0.1` (`LICENSE`)

```
Copyright 2016-2021 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

### `d3-geo@3.1.1` (`LICENSE`)

```
Copyright 2010-2024 Mike Bostock

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.

This license applies to GeographicLib, versions 1.12 and later.

Copyright 2008-2012 Charles Karney

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### `dijkstrajs` (`LICENSE.md`)

````
```
Dijkstra path-finding functions. Adapted from the Dijkstar Python project.

Copyright (C) 2008
  Wyatt Baldwin <self@wyattbaldwin.com>
  All rights reserved

Licensed under the MIT license.

  http://www.opensource.org/licenses/mit-license.php

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
````

### `lodash-es@4.18.1` (`LICENSE`)

```
Copyright OpenJS Foundation and other contributors <https://openjsf.org/>

Based on Underscore.js, copyright Jeremy Ashkenas,
DocumentCloud and Investigative Reporters & Editors <http://underscorejs.org/>

This software consists of voluntary contributions made by many
individuals. For exact contribution history, see the revision history
available at https://github.com/lodash/lodash

The following license applies to all parts of this software except as
documented below:

====

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

====

Copyright and related rights for sample code are waived via CC0. Sample
code is defined as all source code displayed within the prose of the
documentation.

CC0: http://creativecommons.org/publicdomain/zero/1.0/

====

Files located in the node_modules and vendor directories are externally
maintained libraries used by this software which have their own
licenses; we recommend you read them, as their terms may differ from the
terms above.
```

### `lucide-react@0.542.0` (`LICENSE`) — identical file also shipped by: `lucide-react@0.542.0`, `lucide-react@0.555.0`

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

The MIT License (MIT) (for portions derived from Feather)

Copyright (c) 2013-2023 Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `marked@16.4.2` (`LICENSE.md`)

```
# License information

## Contribution License Agreement

If you contribute code to this project, you are implicitly allowing your code
to be distributed under the MIT license. You are also implicitly verifying that
all code is your original work. `</legalese>`

## Marked

Copyright (c) 2018+, MarkedJS (https://github.com/markedjs/)
Copyright (c) 2011-2018, Christopher Jeffrey (https://github.com/chjj/)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

## Markdown

Copyright © 2004, John Gruber
http://daringfireball.net/
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
* Neither the name “Markdown” nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

This software is provided by the copyright holders and contributors “as is” and any express or implied warranties, including, but not limited to, the implied warranties of merchantability and fitness for a particular purpose are disclaimed. In no event shall the copyright owner or contributors be liable for any direct, indirect, incidental, special, exemplary, or consequential damages (including, but not limited to, procurement of substitute goods or services; loss of use, data, or profits; or business interruption) however caused and on any theory of liability, whether in contract, strict liability, or tort (including negligence or otherwise) arising in any way out of the use of this software, even if advised of the possibility of such damage.
```

### `micromark-extension-cjk-friendly-gfm-strikethrough@1.2.3` (`LICENSE`)

```
Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp>

MIT LICENSE

Based on micromark and micromark-core-commonmark & micromark-extension-gfm-strikethrough

(The MIT License)

Copyright (c) Titus Wormer <tituswormer@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
'Software'), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### `micromark-extension-cjk-friendly-util@2.1.1` (`LICENSE`)

```
Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp>

MIT LICENSE

Based on micromark's sub-packages (micromark-util-character, micromark-util-symbol, and micromark-util-classify-character)

(The MIT License)

Copyright (c) Titus Wormer <tituswormer@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
'Software'), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### `micromark-extension-cjk-friendly@1.2.3` (`LICENSE`)

```
Copyright (c) 2025 Tatsunori Uchino <tats.u@live.jp>

MIT LICENSE

Based on micromark and micromark-core-commonmark

(The MIT License)

Copyright (c) Titus Wormer <tituswormer@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
'Software'), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### `radix-ui@1.6.7` (`LICENSE`)

```
MIT License

Copyright (c) 2022 WorkOS

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `remend@1.0.1` (`LICENSE`) — identical file also shipped by: `remend@1.0.1`, `streamdown@1.6.11`

```
Copyright 2023 Vercel, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

### `es-toolkit@1.51.0` (`NOTICE`)

```
es-toolkit

Parts of the test suite and compatibility layer in es-toolkit/compat are
derived from Lodash (https://github.com/lodash/lodash).

Lodash copyright notice and MIT permission notice:

Copyright OpenJS Foundation and other contributors <https://openjsf.org/>

Based on Underscore.js, copyright Jeremy Ashkenas,
DocumentCloud and Investigative Reporters & Editors <http://underscorejs.org/>

This software consists of voluntary contributions made by many
individuals. For exact contribution history, see the revision history
available at https://github.com/lodash/lodash

The following license applies to all parts of this software except as
documented below:

====

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### Packages without a LICENSE file in the published tarball

Seven packages in the tables in sections 1-2 ship no LICENSE/NOTICE file in
their published npm tarball. That was confirmed from the official registry tarball of each
version (the tar member list contains no license file, and the tarball's
`shasum`/`integrity` match the registry metadata; see the method note at the
top of this file). Their license identifiers are the ones declared in their
own `package.json`; the table rows quote the applicable copyright/attribution
line, and the complete texts are reproduced below with the public source each
one was taken from. Sources that upstream added **after** the release are
marked as such - they are not files of the published versions and are quoted
for attribution only.

* `fastdom@1.0.12` - MIT, `Copyright (c) 2016 Wilson Page <wilsonpage@me.com>`
  - from the `## License` section of the `README.md` that ships inside the
    published tarball. That file is byte-identical to the upstream `master`
    copy (the registry `gitHead` `a7b9044d58952b970c8b918dcf0e7c8824ba0ff5`
    has no matching upstream commit and there is no `v1.0.12` tag, so the
    shipped `README.md` itself is the version-verbatim source):
  https://github.com/wilsonpage/fastdom/blob/master/README.md#license.
* `react-remove-scroll-bar@2.3.8` - MIT,
  `Copyright (c) 2025 Anton Korzunov <thekashey@gmail.com>` - **added upstream
  after the release**: the repository `LICENSE` was added in commit
  `7301c160fda44cb8cf2b9fdfde61efad35736196` (2025-05-21), after `2.3.8` was
  published (2024-12-15); it is not a file of the published version:
  https://github.com/theKashey/react-remove-scroll-bar/blob/7301c160fda44cb8cf2b9fdfde61efad35736196/LICENSE.
* `rehype-katex@7.0.1` - MIT,
  `Copyright (c) 2017 Junyoung Choi <fluke8259@gmail.com>` - from the
  repository-root `license` file at the release's `gitHead`
  `88a9497e1ede93b958237c85edbf5651faeca7af` (one file for the whole
  monorepo, covering `packages/rehype-katex`):
  https://github.com/remarkjs/remark-math/blob/88a9497e1ede93b958237c85edbf5651faeca7af/license.
* `remark-math@6.0.0` - MIT,
  `Copyright (c) 2017 Junyoung Choi <fluke8259@gmail.com>` - from the same
  repository-root `license` file, byte-identical at that release's `gitHead`
  `d5d0660b150810a535bbb07eac6cc96a4510aa24`:
  https://github.com/remarkjs/remark-math/blob/d5d0660b150810a535bbb07eac6cc96a4510aa24/license.
* `@hono/node-ws@1.3.1` - MIT,
  `Copyright (c) 2022 - present, Yusuke Wada and Hono contributors` - **added
  upstream after the release**: the repository had no LICENSE/NOTICE file at
  the release's `gitHead` `d0e7b8ee0b8552defc580f30b2a55ad6fbbdfa7a`; the
  root `LICENSE` was added in commit
  `a8e2af4d857aa7fabf290cdf6f67307678e50409` (2026-09-29), after `1.3.1` was
  published (2026-05-01); it is not a file of the published version:
  https://github.com/honojs/middleware/blob/a8e2af4d857aa7fabf290cdf6f67307678e50409/LICENSE.
* `@stricli/core@1.3.0` and `@stricli/auto-complete@1.3.0` - Apache-2.0,
  `Copyright 2024 Bloomberg Finance L.P.` - from the repository-root `LICENSE`
  file at the release's shared `gitHead`
  `4b5802b5370f6b661de945fc7e932ac4e26ae5e0` (the same commit and file for both
  packages; the repository has no NOTICE file, so Apache-2.0 section 4(d)
  adds nothing to redistribute):
  https://github.com/bloomberg/stricli/blob/4b5802b5370f6b661de945fc7e932ac4e26ae5e0/LICENSE.

The six blocks below give the texts byte-for-byte.
`rehype-katex@7.0.1` and `remark-math@6.0.0` share one upstream `license`
file, so the same text is quoted once per release commit and each package
stays anchored at its own `gitHead`; `@stricli/core@1.3.0` and
`@stricli/auto-complete@1.3.0` share one block, since both were released from
the same commit.

### `fastdom@1.0.12` (the package's own `README.md`, `## License` section)

```
## License

(The MIT License)

Copyright (c) 2016 Wilson Page <wilsonpage@me.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the 'Software'), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### `react-remove-scroll-bar@2.3.8` (upstream `LICENSE`, added after the release)

```
MIT License

Copyright (c) 2025 Anton Korzunov <thekashey@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `rehype-katex@7.0.1` (upstream repository-root `license` at `88a9497e1ede93b958237c85edbf5651faeca7af`)

```
(The MIT License)

Copyright (c) 2017 Junyoung Choi <fluke8259@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `remark-math@6.0.0` (upstream repository-root `license` at `d5d0660b150810a535bbb07eac6cc96a4510aa24`)

The same repository-root `license` file as the block above (the two releases
read the identical file):

```
(The MIT License)

Copyright (c) 2017 Junyoung Choi <fluke8259@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `@hono/node-ws@1.3.1` (upstream `LICENSE`, added after the release)

```
MIT License

Copyright (c) 2022 - present, Yusuke Wada and Hono contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### `@stricli/core@1.3.0` and `@stricli/auto-complete@1.3.0` (upstream repository-root `LICENSE` at `4b5802b5370f6b661de945fc7e932ac4e26ae5e0`)

```

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright 2024 Bloomberg Finance L.P.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```

### `typescript@5.9.3` (`ThirdPartyNoticeText.txt`)

TypeScript's package ships a NOTICE-style file (Apache License 2.0 section
4(d)) listing the third-party material incorporated into the TypeScript
software, with the original copyright notices and the licenses under which
Microsoft received it. The file is redistributed unmodified inside the package
(`node_modules/typescript/ThirdPartyNoticeText.txt` in the tarball, next to
`LICENSE.txt`, whose Apache-2.0 text is reproduced in section 5) and is
reproduced verbatim below.

````
/*!----------------- TypeScript ThirdPartyNotices -------------------------------------------------------

The TypeScript software incorporates third party material from the projects listed below. The original copyright notice and the license under which Microsoft received such third party material are set forth below. Microsoft reserves all other rights not expressly granted, whether by implication, estoppel or otherwise.

---------------------------------------------
Third Party Code Components
--------------------------------------------

------------------- DefinitelyTyped --------------------
This file is based on or incorporates material from the projects listed below (collectively "Third Party Code"). Microsoft is not the original author of the Third Party Code. The original copyright notice and the license, under which Microsoft received such Third Party Code, are set forth below. Such licenses and notices are provided for informational purposes only. Microsoft, not the third party, licenses the Third Party Code to you under the terms set forth in the EULA for the Microsoft Product. Microsoft reserves all other rights not expressly granted under this agreement, whether by implication, estoppel or otherwise.
DefinitelyTyped
This project is licensed under the MIT license. Copyrights are respective of each contributor listed at the beginning of each definition file. Provided for Informational Purposes Only

MIT License
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the ""Software""), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
--------------------------------------------------------------------------------------

------------------- Unicode --------------------
UNICODE, INC. LICENSE AGREEMENT - DATA FILES AND SOFTWARE

Unicode Data Files include all data files under the directories
http://www.unicode.org/Public/, http://www.unicode.org/reports/,
http://www.unicode.org/cldr/data/, http://source.icu-project.org/repos/icu/, and
http://www.unicode.org/utility/trac/browser/.

Unicode Data Files do not include PDF online code charts under the
directory http://www.unicode.org/Public/.

Software includes any source code published in the Unicode Standard
or under the directories
http://www.unicode.org/Public/, http://www.unicode.org/reports/,
http://www.unicode.org/cldr/data/, http://source.icu-project.org/repos/icu/, and
http://www.unicode.org/utility/trac/browser/.

NOTICE TO USER: Carefully read the following legal agreement.
BY DOWNLOADING, INSTALLING, COPYING OR OTHERWISE USING UNICODE INC.'S
DATA FILES ("DATA FILES"), AND/OR SOFTWARE ("SOFTWARE"),
YOU UNEQUIVOCALLY ACCEPT, AND AGREE TO BE BOUND BY, ALL OF THE
TERMS AND CONDITIONS OF THIS AGREEMENT.
IF YOU DO NOT AGREE, DO NOT DOWNLOAD, INSTALL, COPY, DISTRIBUTE OR USE
THE DATA FILES OR SOFTWARE.

COPYRIGHT AND PERMISSION NOTICE

Copyright (c) 1991-2017 Unicode, Inc. All rights reserved.
Distributed under the Terms of Use in http://www.unicode.org/copyright.html.

Permission is hereby granted, free of charge, to any person obtaining
a copy of the Unicode data files and any associated documentation
(the "Data Files") or Unicode software and any associated documentation
(the "Software") to deal in the Data Files or Software
without restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, and/or sell copies of
the Data Files or Software, and to permit persons to whom the Data Files
or Software are furnished to do so, provided that either
(a) this copyright and permission notice appear with all copies
of the Data Files or Software, or
(b) this copyright and permission notice appear in associated
Documentation.

THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT OF THIRD PARTY RIGHTS.
IN NO EVENT SHALL THE COPYRIGHT HOLDER OR HOLDERS INCLUDED IN THIS
NOTICE BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL INDIRECT OR CONSEQUENTIAL
DAMAGES, OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THE DATA FILES OR SOFTWARE.

Except as contained in this notice, the name of a copyright holder
shall not be used in advertising or otherwise to promote the sale,
use or other dealings in these Data Files or Software without prior
written authorization of the copyright holder.
-------------------------------------------------------------------------------------

-------------------Document Object Model-----------------------------
DOM 

W3C License
This work is being provided by the copyright holders under the following license.
By obtaining and/or copying this work, you (the licensee) agree that you have read, understood, and will comply with the following terms and conditions.
Permission to copy, modify, and distribute this work, with or without modification, for any purpose and without fee or royalty is hereby granted, provided that you include the following 
on ALL copies of the work or portions thereof, including modifications:
* The full text of this NOTICE in a location viewable to users of the redistributed or derivative work.
* Any pre-existing intellectual property disclaimers, notices, or terms and conditions. If none exist, the W3C Software and Document Short Notice should be included.
* Notice of any changes or modifications, through a copyright statement on the new code or document such as "This software or document includes material copied from or derived 
from [title and URI of the W3C document]. Copyright © [YEAR] W3C® (MIT, ERCIM, Keio, Beihang)." 
Disclaimers
THIS WORK IS PROVIDED "AS IS," AND COPYRIGHT HOLDERS MAKE NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO, WARRANTIES OF MERCHANTABILITY OR 
FITNESS FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF THE SOFTWARE OR DOCUMENT WILL NOT INFRINGE ANY THIRD PARTY PATENTS, COPYRIGHTS, TRADEMARKS OR OTHER RIGHTS.
COPYRIGHT HOLDERS WILL NOT BE LIABLE FOR ANY DIRECT, INDIRECT, SPECIAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF ANY USE OF THE SOFTWARE OR DOCUMENT.
The name and trademarks of copyright holders may NOT be used in advertising or publicity pertaining to the work without specific, written prior permission. 
Title to copyright in this work will at all times remain with copyright holders.

---------

DOM
Copyright © 2018 WHATWG (Apple, Google, Mozilla, Microsoft). This work is licensed under a Creative Commons Attribution 4.0 International License: Attribution 4.0 International 
======================================================================= 
Creative Commons Corporation ("Creative Commons") is not a law firm and does not provide legal services or legal advice. Distribution of Creative Commons public licenses does not create a lawyer-client or other relationship. Creative Commons makes its licenses and related information available on an "as-is" basis. Creative Commons gives no warranties regarding its licenses, any material licensed under their terms and conditions, or any related information. Creative Commons disclaims all liability for damages resulting from their use to the fullest extent possible. Using Creative Commons Public Licenses Creative Commons public licenses provide a standard set of terms and conditions that creators and other rights holders may use to share original works of authorship and other material subject to copyright and certain other rights specified in the public license below. The following considerations are for informational purposes only, are not exhaustive, and do not form part of our licenses. Considerations for licensors: Our public licenses are intended for use by those authorized to give the public permission to use material in ways otherwise restricted by copyright and certain other rights. Our licenses are irrevocable. Licensors should read and understand the terms and conditions of the license they choose before applying it. Licensors should also secure all rights necessary before applying our licenses so that the public can reuse the material as expected. Licensors should clearly mark any material not subject to the license. This includes other CC- licensed material, or material used under an exception or limitation to copyright. More considerations for licensors:

wiki.creativecommons.org/Considerations_for_licensors Considerations for the public: By using one of our public licenses, a licensor grants the public permission to use the licensed material under specified terms and conditions. If the licensor's permission is not necessary for any reason--for example, because of any applicable exception or limitation to copyright--then that use is not regulated by the license. Our licenses grant only permissions under copyright and certain other rights that a licensor has authority to grant. Use of the licensed material may still be restricted for other reasons, including because others have copyright or other rights in the material. A licensor may make special requests, such as asking that all changes be marked or described. Although not required by our licenses, you are encouraged to respect those requests where reasonable. More_considerations for the public: wiki.creativecommons.org/Considerations_for_licensees ======================================================================= 
Creative Commons Attribution 4.0 International Public License By exercising the Licensed Rights (defined below), You accept and agree to be bound by the terms and conditions of this Creative Commons Attribution 4.0 International Public License ("Public License"). To the extent this Public License may be interpreted as a contract, You are granted the Licensed Rights in consideration of Your acceptance of these terms and conditions, and the Licensor grants You such rights in consideration of benefits the Licensor receives from making the Licensed Material available under these terms and conditions. Section 1 -- Definitions. a. Adapted Material means material subject to Copyright and Similar Rights that is derived from or based upon the Licensed Material and in which the Licensed Material is translated, altered, arranged, transformed, or otherwise modified in a manner requiring permission under the Copyright and Similar Rights held by the Licensor. For purposes of this Public License, where the Licensed Material is a musical work, performance, or sound recording, Adapted Material is always produced where the Licensed Material is synched in timed relation with a moving image. b. Adapter's License means the license You apply to Your Copyright and Similar Rights in Your contributions to Adapted Material in accordance with the terms and conditions of this Public License. c. Copyright and Similar Rights means copyright and/or similar rights closely related to copyright including, without limitation, performance, broadcast, sound recording, and Sui Generis Database Rights, without regard to how the rights are labeled or categorized. For purposes of this Public License, the rights specified in Section 2(b)(1)-(2) are not Copyright and Similar Rights. d. Effective Technological Measures means those measures that, in the absence of proper authority, may not be circumvented under laws fulfilling obligations under Article 11 of the WIPO Copyright Treaty adopted on December 20, 1996, and/or similar international agreements. e. Exceptions and Limitations means fair use, fair dealing, and/or any other exception or limitation to Copyright and Similar Rights that applies to Your use of the Licensed Material. f. Licensed Material means the artistic or literary work, database, or other material to which the Licensor applied this Public License. g. Licensed Rights means the rights granted to You subject to the terms and conditions of this Public License, which are limited to all Copyright and Similar Rights that apply to Your use of the Licensed Material and that the Licensor has authority to license. h. Licensor means the individual(s) or entity(ies) granting rights under this Public License. i. Share means to provide material to the public by any means or process that requires permission under the Licensed Rights, such as reproduction, public display, public performance, distribution, dissemination, communication, or importation, and to make material available to the public including in ways that members of the public may access the material from a place and at a time individually chosen by them. j. Sui Generis Database Rights means rights other than copyright resulting from Directive 96/9/EC of the European Parliament and of the Council of 11 March 1996 on the legal protection of databases, as amended and/or succeeded, as well as other essentially equivalent rights anywhere in the world. k. You means the individual or entity exercising the Licensed Rights under this Public License. Your has a corresponding meaning. Section 2 -- Scope. a. License grant. 1. Subject to the terms and conditions of this Public License, the Licensor hereby grants You a worldwide, royalty-free, non-sublicensable, non-exclusive, irrevocable license to exercise the Licensed Rights in the Licensed Material to: a. reproduce and Share the Licensed Material, in whole or in part; and b. produce, reproduce, and Share Adapted Material. 2. Exceptions and Limitations. For the avoidance of doubt, where Exceptions and Limitations apply to Your use, this Public License does not apply, and You do not need to comply with its terms and conditions. 3. Term. The term of this Public License is specified in Section 6(a). 4. Media and formats; technical modifications allowed. The Licensor authorizes You to exercise the Licensed Rights in all media and formats whether now known or hereafter created, and to make technical modifications necessary to do so. The Licensor waives and/or agrees not to assert any right or authority to forbid You from making technical modifications necessary to exercise the Licensed Rights, including technical modifications necessary to circumvent Effective Technological Measures. For purposes of this Public License, simply making modifications authorized by this Section 2(a) (4) never produces Adapted Material. 5. Downstream recipients. a. Offer from the Licensor -- Licensed Material. Every recipient of the Licensed Material automatically receives an offer from the Licensor to exercise the Licensed Rights under the terms and conditions of this Public License. b. No downstream restrictions. You may not offer or impose any additional or different terms or conditions on, or apply any Effective Technological Measures to, the Licensed Material if doing so restricts exercise of the Licensed Rights by any recipient of the Licensed Material. 6. No endorsement. Nothing in this Public License constitutes or may be construed as permission to assert or imply that You are, or that Your use of the Licensed Material is, connected with, or sponsored, endorsed, or granted official status by, the Licensor or others designated to receive attribution as provided in Section 3(a)(1)(A)(i). b. Other rights. 1. Moral rights, such as the right of integrity, are not licensed under this Public License, nor are publicity, privacy, and/or other similar personality rights; however, to the extent possible, the Licensor waives and/or agrees not to assert any such rights held by the Licensor to the limited extent necessary to allow You to exercise the Licensed Rights, but not otherwise. 2. Patent and trademark rights are not licensed under this Public License. 3. To the extent possible, the Licensor waives any right to collect royalties from You for the exercise of the Licensed Rights, whether directly or through a collecting society under any voluntary or waivable statutory or compulsory licensing scheme. In all other cases the Licensor expressly reserves any right to collect such royalties. Section 3 -- License Conditions. Your exercise of the Licensed Rights is expressly made subject to the following conditions. a. Attribution. 1. If You Share the Licensed Material (including in modified form), You must: a. retain the following if it is supplied by the Licensor with the Licensed Material: i. identification of the creator(s) of the Licensed Material and any others designated to receive attribution, in any reasonable manner requested by the Licensor (including by pseudonym if designated); ii. a copyright notice; iii. a notice that refers to this Public License; iv. a notice that refers to the disclaimer of warranties; v. a URI or hyperlink to the Licensed Material to the extent reasonably practicable; b. indicate if You modified the Licensed Material and retain an indication of any previous modifications; and c. indicate the Licensed Material is licensed under this Public License, and include the text of, or the URI or hyperlink to, this Public License. 2. You may satisfy the conditions in Section 3(a)(1) in any reasonable manner based on the medium, means, and context in which You Share the Licensed Material. For example, it may be reasonable to satisfy the conditions by providing a URI or hyperlink to a resource that includes the required information. 3. If requested by the Licensor, You must remove any of the information required by Section 3(a)(1)(A) to the extent reasonably practicable. 4. If You Share Adapted Material You produce, the Adapter's License You apply must not prevent recipients of the Adapted Material from complying with this Public License. Section 4 -- Sui Generis Database Rights. Where the Licensed Rights include Sui Generis Database Rights that apply to Your use of the Licensed Material: a. for the avoidance of doubt, Section 2(a)(1) grants You the right to extract, reuse, reproduce, and Share all or a substantial portion of the contents of the database; b. if You include all or a substantial portion of the database contents in a database in which You have Sui Generis Database Rights, then the database in which You have Sui Generis Database Rights (but not its individual contents) is Adapted Material; and c. You must comply with the conditions in Section 3(a) if You Share all or a substantial portion of the contents of the database. For the avoidance of doubt, this Section 4 supplements and does not replace Your obligations under this Public License where the Licensed Rights include other Copyright and Similar Rights. Section 5 -- Disclaimer of Warranties and Limitation of Liability. a. UNLESS OTHERWISE SEPARATELY UNDERTAKEN BY THE LICENSOR, TO THE EXTENT POSSIBLE, THE LICENSOR OFFERS THE LICENSED MATERIAL AS-IS AND AS-AVAILABLE, AND MAKES NO REPRESENTATIONS OR WARRANTIES OF ANY KIND CONCERNING THE LICENSED MATERIAL, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHER. THIS INCLUDES, WITHOUT LIMITATION, WARRANTIES OF TITLE, MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, ABSENCE OF LATENT OR OTHER DEFECTS, ACCURACY, OR THE PRESENCE OR ABSENCE OF ERRORS, WHETHER OR NOT KNOWN OR DISCOVERABLE. WHERE DISCLAIMERS OF WARRANTIES ARE NOT ALLOWED IN FULL OR IN PART, THIS DISCLAIMER MAY NOT APPLY TO YOU. b. TO THE EXTENT POSSIBLE, IN NO EVENT WILL THE LICENSOR BE LIABLE TO YOU ON ANY LEGAL THEORY (INCLUDING, WITHOUT LIMITATION, NEGLIGENCE) OR OTHERWISE FOR ANY DIRECT, SPECIAL, INDIRECT, INCIDENTAL, CONSEQUENTIAL, PUNITIVE, EXEMPLARY, OR OTHER LOSSES, COSTS, EXPENSES, OR DAMAGES ARISING OUT OF THIS PUBLIC LICENSE OR USE OF THE LICENSED MATERIAL, EVEN IF THE LICENSOR HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH LOSSES, COSTS, EXPENSES, OR DAMAGES. WHERE A LIMITATION OF LIABILITY IS NOT ALLOWED IN FULL OR IN PART, THIS LIMITATION MAY NOT APPLY TO YOU. c. The disclaimer of warranties and limitation of liability provided above shall be interpreted in a manner that, to the extent possible, most closely approximates an absolute disclaimer and waiver of all liability. Section 6 -- Term and Termination. a. This Public License applies for the term of the Copyright and Similar Rights licensed here. However, if You fail to comply with this Public License, then Your rights under this Public License terminate automatically. b. Where Your right to use the Licensed Material has terminated under Section 6(a), it reinstates: 1. automatically as of the date the violation is cured, provided it is cured within 30 days of Your discovery of the violation; or 2. upon express reinstatement by the Licensor. For the avoidance of doubt, this Section 6(b) does not affect any right the Licensor may have to seek remedies for Your violations of this Public License. c. For the avoidance of doubt, the Licensor may also offer the Licensed Material under separate terms or conditions or stop distributing the Licensed Material at any time; however, doing so will not terminate this Public License. d. Sections 1, 5, 6, 7, and 8 survive termination of this Public License. Section 7 -- Other Terms and Conditions. a. The Licensor shall not be bound by any additional or different terms or conditions communicated by You unless expressly agreed. b. Any arrangements, understandings, or agreements regarding the Licensed Material not stated herein are separate from and independent of the terms and conditions of this Public License. Section 8 -- Interpretation. a. For the avoidance of doubt, this Public License does not, and shall not be interpreted to, reduce, limit, restrict, or impose conditions on any use of the Licensed Material that could lawfully be made without permission under this Public License. b. To the extent possible, if any provision of this Public License is deemed unenforceable, it shall be automatically reformed to the minimum extent necessary to make it enforceable. If the provision cannot be reformed, it shall be severed from this Public License without affecting the enforceability of the remaining terms and conditions. c. No term or condition of this Public License will be waived and no failure to comply consented to unless expressly agreed to by the Licensor. d. Nothing in this Public License constitutes or may be interpreted as a limitation upon, or waiver of, any privileges and immunities that apply to the Licensor or You, including from the legal processes of any jurisdiction or authority. ======================================================================= Creative Commons is not a party to its public licenses. Notwithstanding, Creative Commons may elect to apply one of its public licenses to material it publishes and in those instances will be considered the "Licensor." Except for the limited purpose of indicating that material is shared under a Creative Commons public license or as otherwise permitted by the Creative Commons policies published at creativecommons.org/policies, Creative Commons does not authorize the use of the trademark "Creative Commons" or any other trademark or logo of Creative Commons without its prior written consent including, without limitation, in connection with any unauthorized modifications to any of its public licenses or any other arrangements, understandings, or agreements concerning use of licensed material. For the avoidance of doubt, this paragraph does not form part of the public licenses. Creative Commons may be contacted at creativecommons.org.

--------------------------------------------------------------------------------

----------------------Web Background Synchronization------------------------------

Web Background Synchronization Specification
Portions of spec © by W3C

W3C Community Final Specification Agreement 
To secure commitments from participants for the full text of a Community or Business Group Report, the group may call for voluntary commitments to the following terms; a "summary" is 
available. See also the related "W3C Community Contributor License Agreement".
1. The Purpose of this Agreement.
This Agreement sets forth the terms under which I make certain copyright and patent rights available to you for your implementation of the Specification. 
Any other capitalized terms not specifically defined herein have the same meaning as those terms have in the "W3C Patent Policy", and if not defined there, in the "W3C Process Document".
2. Copyrights. 
2.1. Copyright Grant. I grant to you a perpetual (for the duration of the applicable copyright), worldwide, non-exclusive, no-charge, royalty-free, copyright license, without any obligation for accounting to me, to reproduce, prepare derivative works of, publicly display, publicly perform, sublicense, distribute, and implement the Specification to the full extent of my copyright interest in the Specification. 
2.2. Attribution. As a condition of the copyright grant, you must include an attribution to the Specification in any derivative work you make based on the Specification. That attribution must include, at minimum, the Specification name and version number.
3. Patents. 
3.1. Patent Licensing Commitment. I agree to license my Essential Claims under the W3C Community RF Licensing Requirements. This requirement includes Essential Claims that I own and any that I have the right to license without obligation of payment or other consideration to an unrelated third party. W3C Community RF Licensing Requirements obligations made concerning the Specification and described in this policy are binding on me for the life of the patents in question and encumber the patents containing Essential Claims, regardless of changes in participation status or W3C Membership. I also agree to license my Essential Claims under the W3C Community RF Licensing Requirements in derivative works of the Specification so long as all normative portions of the Specification are maintained and that this licensing commitment does not extend to any portion of the derivative work that was not included in the Specification.
3.2. Optional, Additional Patent Grant. In addition to the provisions of Section 3.1, I may also, at my option, make certain intellectual property rights infringed by implementations of the Specification, including Essential Claims, available by providing those terms via the W3C Web site.
4. No Other Rights. Except as specifically set forth in this Agreement, no other express or implied patent, trademark, copyright, or other property rights are granted under this Agreement, including by implication, waiver, or estoppel.
5. Antitrust Compliance. I acknowledge that I may compete with other participants, that I am under no obligation to implement the Specification, that each participant is free to develop competing technologies and standards, and that each party is free to license its patent rights to third parties, including for the purpose of enabling competing technologies and standards.
6. Non-Circumvention. I agree that I will not intentionally take or willfully assist any third party to take any action for the purpose of circumventing my obligations under this Agreement.
7. Transition to W3C Recommendation Track. The Specification developed by the Project may transition to the W3C Recommendation Track. The W3C Team is responsible for notifying me that a Corresponding Working Group has been chartered. I have no obligation to join the Corresponding Working Group. If the Specification developed by the Project transitions to the W3C Recommendation Track, the following terms apply: 
7.1. If I join the Corresponding Working Group. If I join the Corresponding Working Group, I will be subject to all W3C rules, obligations, licensing commitments, and policies that govern that Corresponding Working Group.
7.2. If I Do Not Join the Corresponding Working Group. 
7.2.1. Licensing Obligations to Resulting Specification. If I do not join the Corresponding Working Group, I agree to offer patent licenses according to the W3C Royalty-Free licensing requirements described in Section 5 of the W3C Patent Policy for the portions of the Specification included in the resulting Recommendation. This licensing commitment does not extend to any portion of an implementation of the Recommendation that was not included in the Specification. This licensing commitment may not be revoked but may be modified through the exclusion process defined in Section 4 of the W3C Patent Policy. I am not required to join the Corresponding Working Group to exclude patents from the W3C Royalty-Free licensing commitment, but must otherwise follow the normal exclusion procedures defined by the W3C Patent Policy. The W3C Team will notify me of any Call for Exclusion in the Corresponding Working Group as set forth in Section 4.5 of the W3C Patent Policy.
7.2.2. No Disclosure Obligation. If I do not join the Corresponding Working Group, I have no patent disclosure obligations outside of those set forth in Section 6 of the W3C Patent Policy.
8. Conflict of Interest. I will disclose significant relationships when those relationships might reasonably be perceived as creating a conflict of interest with my role. I will notify W3C of any change in my affiliation using W3C-provided mechanisms.
9. Representations, Warranties and Disclaimers. I represent and warrant that I am legally entitled to grant the rights and promises set forth in this Agreement. IN ALL OTHER RESPECTS THE SPECIFICATION IS PROVIDED “AS IS.” The entire risk as to implementing or otherwise using the Specification is assumed by the implementer and user. Except as stated herein, I expressly disclaim any warranties (express, implied, or otherwise), including implied warranties of merchantability, non-infringement, fitness for a particular purpose, or title, related to the Specification. IN NO EVENT WILL ANY PARTY BE LIABLE TO ANY OTHER PARTY FOR LOST PROFITS OR ANY FORM OF INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES OF ANY CHARACTER FROM ANY CAUSES OF ACTION OF ANY KIND WITH RESPECT TO THIS AGREEMENT, WHETHER BASED ON BREACH OF CONTRACT, TORT (INCLUDING NEGLIGENCE), OR OTHERWISE, AND WHETHER OR NOT THE OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. All of my obligations under Section 3 regarding the transfer, successors in interest, or assignment of Granted Claims will be satisfied if I notify the transferee or assignee of any patent that I know contains Granted Claims of the obligations under Section 3. Nothing in this Agreement requires me to undertake a patent search.
10. Definitions. 
10.1. Agreement. “Agreement” means this W3C Community Final Specification Agreement.
10.2. Corresponding Working Group. “Corresponding Working Group” is a W3C Working Group that is chartered to develop a Recommendation, as defined in the W3C Process Document, that takes the Specification as an input.
10.3. Essential Claims. “Essential Claims” shall mean all claims in any patent or patent application in any jurisdiction in the world that would necessarily be infringed by implementation of the Specification. A claim is necessarily infringed hereunder only when it is not possible to avoid infringing it because there is no non-infringing alternative for implementing the normative portions of the Specification. Existence of a non-infringing alternative shall be judged based on the state of the art at the time of the publication of the Specification. The following are expressly excluded from and shall not be deemed to constitute Essential Claims: 
10.3.1. any claims other than as set forth above even if contained in the same patent as Essential Claims; and
10.3.2. claims which would be infringed only by: 
portions of an implementation that are not specified in the normative portions of the Specification, or
enabling technologies that may be necessary to make or use any product or portion thereof that complies with the Specification and are not themselves expressly set forth in the Specification (e.g., semiconductor manufacturing technology, compiler technology, object-oriented technology, basic operating system technology, and the like); or
the implementation of technology developed elsewhere and merely incorporated by reference in the body of the Specification.
10.3.3. design patents and design registrations.
For purposes of this definition, the normative portions of the Specification shall be deemed to include only architectural and interoperability requirements. Optional features in the RFC 2119 sense are considered normative unless they are specifically identified as informative. Implementation examples or any other material that merely illustrate the requirements of the Specification are informative, rather than normative.
10.4. I, Me, or My. “I,” “me,” or “my” refers to the signatory.
10.5 Project. “Project” means the W3C Community Group or Business Group for which I executed this Agreement.
10.6. Specification. “Specification” means the Specification identified by the Project as the target of this agreement in a call for Final Specification Commitments. W3C shall provide the authoritative mechanisms for the identification of this Specification.
10.7. W3C Community RF Licensing Requirements. “W3C Community RF Licensing Requirements” license shall mean a non-assignable, non-sublicensable license to make, have made, use, sell, have sold, offer to sell, import, and distribute and dispose of implementations of the Specification that: 
10.7.1. shall be available to all, worldwide, whether or not they are W3C Members;
10.7.2. shall extend to all Essential Claims owned or controlled by me;
10.7.3. may be limited to implementations of the Specification, and to what is required by the Specification;
10.7.4. may be conditioned on a grant of a reciprocal RF license (as defined in this policy) to all Essential Claims owned or controlled by the licensee. A reciprocal license may be required to be available to all, and a reciprocal license may itself be conditioned on a further reciprocal license from all.
10.7.5. may not be conditioned on payment of royalties, fees or other consideration;
10.7.6. may be suspended with respect to any licensee when licensor issued by licensee for infringement of claims essential to implement the Specification or any W3C Recommendation;
10.7.7. may not impose any further conditions or restrictions on the use of any technology, intellectual property rights, or other restrictions on behavior of the licensee, but may include reasonable, customary terms relating to operation or maintenance of the license relationship such as the following: choice of law and dispute resolution;
10.7.8. shall not be considered accepted by an implementer who manifests an intent not to accept the terms of the W3C Community RF Licensing Requirements license as offered by the licensor.
10.7.9. The RF license conforming to the requirements in this policy shall be made available by the licensor as long as the Specification is in effect. The term of such license shall be for the life of the patents in question.
I am encouraged to provide a contact from which licensing information can be obtained and other relevant licensing information. Any such information will be made publicly available. 
10.8. You or Your. “You,” “you,” or “your” means any person or entity who exercises copyright or patent rights granted under this Agreement, and any person that person or entity controls.

-------------------------------------------------------------------------------------

------------------- WebGL -----------------------------
Copyright (c) 2018 The Khronos Group Inc.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and/or associated documentation files (the
"Materials"), to deal in the Materials without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Materials, and to
permit persons to whom the Materials are furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Materials.

THE MATERIALS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
MATERIALS OR THE USE OR OTHER DEALINGS IN THE MATERIALS.
------------------------------------------------------

------------- End of ThirdPartyNotices ------------------------------------------- */

````

## 7. Packaging notes - what must ship with each archive

* **Extension zip** (`just pack-extension`): copy `chrome-acp/LICENSE` and this
  file to `packages/chrome-extension/LICENSE` and
  `packages/chrome-extension/THIRD_PARTY_NOTICES.md`, and add both to the `zip`
  argument (next to `manifest.json`, `icons`, `rules`, `dist`). The vendored
  pdf.js license already ships inside `dist/pdf/LICENSE`.
* **Proxy tarball** (`just pack-proxy`): copy `chrome-acp/LICENSE`, this file,
  `packages/proxy-server/package.json` and the committed
  `packages/proxy-server/package-lock.json` into the staging directory, then run
  `npm ci --omit=dev --ignore-scripts` there, so the tarball contains
  `LICENSE`, `THIRD_PARTY_NOTICES.md`, `dist/`, `public/`, `package.json`,
  `package-lock.json` and the pinned production `node_modules/` installed from
  it. The installed npm packages carry their own LICENSE files under
  `node_modules/` where the published package ships one; for the three proxy
  packages that ship none, the full texts are reproduced in section 6.
* **PWA**: copy `chrome-acp/LICENSE` and this file into
  `packages/proxy-server/public/` so the PWA served by the proxy links to them.