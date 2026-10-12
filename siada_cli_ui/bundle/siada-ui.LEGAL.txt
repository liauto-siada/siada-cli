# Third-Party Notices - siada-cli-ui terminal UI bundle

This file covers the third-party JavaScript that is bundled into the terminal
UI shipped by Siada CLI, and the license texts that apply to it.

## Scope and method

* Component: `siada_cli_ui/bundle/siada-ui.js` - the minified esbuild bundle of
  `siada_cli_ui/src/cli.ts` (pinned as `process.env.CLI_VERSION` from
  `pyproject.toml` at build time).
* Bundled package set (audited): every input recorded in the bundle's esbuild
  metafile (`siada_cli_ui/bundle/esbuild-meta.json`; 999 inputs in the current
  build, including the virtual module `devtools-stub:devtools-stub`) is assigned
  to its owning npm package. The virtual module is excluded; each of the 998
  file inputs is resolved by walking up from the file
  to the nearest ancestor `package.json` that declares both `name` and
  `version`. Nested `package.json` files without a package name and version
  (`diff/libesm/package.json`, `highlight.js/es/package.json`) are skipped and
  resolution continues upward. The result is 52 third-party install roots and
  50 distinct `name@version` entries, all matching the committed
  `siada_cli_ui/package-lock.json`, with 0 file inputs left without an owning
  package. `devDependencies` and type-only `@types/*` packages contribute no
  code to the bundle and are not part of this set.
* Additional upstream attributions: the second table below lists packages that
  are recorded in `siada_cli_ui/package-lock.json` but are not among the current
  bundle inputs (a subset of the runtime dependency closure, plus one `dev`-flagged
  package). They are kept from earlier revisions of this notice so the
  attribution stays over-inclusive; this notice does not claim that the whole
  locked dependency tree is inlined into the bundle.
* Verification: every bundled package appears in the first table with the SPDX
  identifier declared by its `package.json` and the copyright notice quoted
  verbatim from its shipped `LICENSE` file or source header, and every shipped license file
  matches one of the license texts reproduced below. The only bundled package
  whose published tarball has no LICENSE file is `yoga-layout` (see Notes).
* Data source: the `package.json` and `LICENSE` files of the packages as
  published on npm (installed under `siada_cli_ui/node_modules/`). License
  identifiers are the packages' own SPDX identifiers; the copyright/attribution
  lines are quoted verbatim from the shipped license files.
* `esbuild` preserves the inlined files' `@license` banners at the end of the
  bundle (React / react-reconciler / scheduler - MIT - Copyright (c) Meta
  Platforms, Inc. and affiliates; `@jrichman/ink` scroll.js / layout.js /
  selection.js - Apache-2.0 - Copyright 2025 Google LLC; `fzf` - BSD 3-Clause -
  Copyright (c) 2021 Ajit).

## Packages in the bundle inputs

The rows below are the complete set of packages that own an input file of
`bundle/esbuild-meta.json` for `bundle/siada-ui.js`: 52 third-party install
roots resolving to 50 distinct `name@version` entries (nested installs that
share a version, e.g. `ansi-regex@6.2.2` under both `wrap-ansi/node_modules`
and `string-width/node_modules`, share a row). Versions match
`siada_cli_ui/package-lock.json`.

| Package | Version | License | Copyright / attribution (verbatim from the package's LICENSE) |
|---|---|---|---|
| `@alcalzone/ansi-tokenize` | 0.2.5 | MIT | Copyright (c) 2020-2026 AlCalzone |
| `@jrichman/ink` | 6.4.11 | MIT | Copyright (c) Vadym Demedes <vadimdemedes@hey.com> (github.com/vadimdemedes) |
| `ansi-escapes` | 7.3.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `ansi-regex` | 6.2.2 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `ansi-styles` | 6.2.3 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `auto-bind` | 5.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `chalk` | 5.6.2 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `cli-boxes` | 3.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `cli-cursor` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `cli-spinners` | 2.9.2 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `cli-truncate` | 5.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `code-excerpt` | 4.0.0 | MIT | Copyright (c) Vadim Demedes <vdemedes@gmail.com> (github.com/vadimdemedes) |
| `commander` | 12.1.0 | MIT | Copyright (c) 2011 TJ Holowaychuk <tj@vision-media.ca> |
| `convert-to-spaces` | 2.0.1 | MIT | Copyright (c) Vadim Demedes <vdemedes@gmail.com> (https://vadimdemedes.com) |
| `devlop` | 1.1.0 | MIT | Copyright (c) 2023 Titus Wormer <tituswormer@gmail.com> |
| `diff` | 9.0.0 | BSD-3-Clause | Copyright (c) 2009-2015, Kevin Decker <kpdecker@gmail.com> |
| `emoji-regex` | 10.6.0 | MIT | Copyright Mathias Bynens <https://mathiasbynens.be/> |
| `environment` | 1.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `es-toolkit` | 1.45.1 | MIT | Copyright (c) 2024 Viva Republica, Inc<br>Copyright OpenJS Foundation and other contributors |
| `escape-string-regexp` | 2.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `fzf` | 0.5.2 | BSD-3-Clause | Copyright (c) 2021, Ajit |
| `get-east-asian-width` | 1.5.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `highlight.js` | 11.11.1 | BSD-3-Clause | Copyright (c) 2006, Ivan Sagalaev. |
| `indent-string` | 5.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `ink` | 6.8.0 | MIT | Copyright (c) Vadym Demedes <vadimdemedes@hey.com> (https://github.com/vadimdemedes)<br>Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `ink-spinner` | 5.0.0 | MIT | Copyright (c) Vadym Demedes <vadimdemedes@hey.com> (github.com/vadimdemedes) |
| `is-fullwidth-code-point` | 5.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `is-in-ci` | 2.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `lowlight` | 3.3.0 | MIT | Copyright (c) Titus Wormer <tituswormer@gmail.com> |
| `mimic-fn` | 2.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `mnemonist` | 0.40.3 | MIT | Copyright (c) 2016 Guillaume Plique (Yomguithereal) |
| `obliterator` | 2.0.5 | MIT | Copyright (c) 2017-2021 Guillaume Plique (Yomguithereal) |
| `onetime` | 5.1.2 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `patch-console` | 2.0.0 | MIT | Copyright (c) Vadim Demedes <vadimdemedes@hey.com> (https://vadimdemedes.com) |
| `react` | 19.2.4 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `react-reconciler` | 0.32.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `react-reconciler` | 0.33.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `restore-cursor` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `scheduler` | 0.26.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `scheduler` | 0.27.0 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `signal-exit` | 3.0.7 | ISC | Copyright (c) 2015, Contributors |
| `slice-ansi` | 8.0.0 | MIT | Copyright (c) DC <threedeecee@gmail.com><br>Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `stack-utils` | 2.0.6 | MIT | Copyright (c) 2016-2022 Isaac Z. Schlueter <i@izs.me>, James Talmage <james@talmage.io> (github.com/jamestalmage), and Contributors |
| `string-width` | 7.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `string-width` | 8.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `strip-ansi` | 7.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `terminal-size` | 4.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `widest-line` | 6.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `wrap-ansi` | 9.0.2 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `yoga-layout` | 3.2.1 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. *(from its source headers)* |

## Additional upstream attributions

These packages are recorded in `siada_cli_ui/package-lock.json` but are not
among the current `bundle/esbuild-meta.json` inputs: 32 belong to the runtime
dependency closure of `siada_cli_ui/package.json`, and
`escape-string-regexp@4.0.0` is flagged `dev` (pulled in by the `eslint` dev
tree). They are retained from earlier revisions of this notice so that the
attribution stays over-inclusive; this notice does not claim that the whole
locked dependency tree is inlined into the bundle. Several packages appear
here in addition to a different bundled version (`ansi-regex`, `cli-truncate`,
`escape-string-regexp`, `react-reconciler`, `scheduler`, `slice-ansi`,
`string-width`, `strip-ansi`); each installed version is listed separately.

| Package | Version | License | Copyright / attribution (verbatim from the package's LICENSE) |
|---|---|---|---|
| `@agentclientprotocol/sdk` | 0.12.0 | Apache-2.0 | Copyright 2025 Zed Industries, Inc. and contributors |
| `@sindresorhus/is` | 4.6.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `ansi-regex` | 5.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `ansicolors` | 0.3.2 | MIT | Copyright 2013 Thorsten Lorenz. |
| `cardinal` | 2.1.1 | MIT | Copyright 2012 Thorsten Lorenz. |
| `chalk-template` | 1.1.2 | MIT | Copyright (c) Josh Junon<br>Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `char-regex` | 1.0.2 | MIT | Copyright (c) 2019 Richie Bendall |
| `cli-table3` | 0.6.5 | MIT | Copyright (c) 2014 James Talmage <james.talmage@jrtechnical.com> |
| `cli-truncate` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `dequal` | 2.0.3 | MIT | Copyright (c) Luke Edwards <luke.edwards05@gmail.com> (lukeed.com) |
| `emojilib` | 2.4.0 | MIT | Copyright (c) 2014 Mu-An Chiou |
| `escape-string-regexp` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `esprima` | 4.0.1 | BSD-2-Clause | Copyright JS Foundation and other contributors, https://js.foundation/ |
| `figures` | 6.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `has-flag` | 4.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `ink-markdown` | 1.0.4 | MIT | *package.json author:* Cameron Hunter <hello@cameronhunter.co.uk> |
| `ink-select-input` | 6.2.0 | MIT | Copyright (c) Vadim Demedes <vdemedes@gmail.com> (github.com/vadimdemedes) |
| `ink-text-input` | 6.0.0 | MIT | Copyright (c) Vadym Demedes <vadimdemedes@hey.com> (github.com/vadimdemedes) |
| `is-unicode-supported` | 2.1.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `marked` | 9.1.6 | MIT | Copyright (c) 2018+, MarkedJS (https://github.com/markedjs/)<br>Copyright (c) 2011-2018, Christopher Jeffrey (https://github.com/chjj/)<br>Copyright © 2004, John Gruber |
| `marked-terminal` | 6.2.0 | MIT | Copyright (c) 2017 Mikael Brevik |
| `node-emoji` | 2.2.0 | MIT | Copyright (c) 2014-2023 Daniel Bugl |
| `react-dom` | 19.2.4 | MIT | Copyright (c) Meta Platforms, Inc. and affiliates. |
| `redeyed` | 2.1.1 | MIT | Copyright 2012 Thorsten Lorenz. |
| `skin-tone` | 2.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `slice-ansi` | 7.1.2 | MIT | Copyright (c) DC <threedeecee@gmail.com><br>Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `strip-ansi` | 6.0.1 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `supports-color` | 7.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (sindresorhus.com) |
| `supports-hyperlinks` | 3.2.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com)<br>Copyright (c) James Talmage <james@talmage.io> (https://github.com/jamestalmage) |
| `to-rotated` | 1.0.0 | MIT | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `type-fest` | 4.41.0 | MIT *(dual-licensed; this option chosen)* | Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com) |
| `unicode-emoji-modifier-base` | 1.0.0 | MIT | Copyright Mathias Bynens <https://mathiasbynens.be/> |
| `ws` | 8.19.0 | MIT | Copyright (c) 2011 Einar Otto Stangvik <einaros@gmail.com><br>Copyright (c) 2013 Arnout Kazemier and contributors<br>Copyright (c) 2016 Luigi Pinca and contributors |

## License texts

### MIT

The text below is reproduced from `@jrichman/ink` (`license`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
MIT License

Copyright (c) Vadym Demedes <vadimdemedes@hey.com> (github.com/vadimdemedes)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### ISC

The text below is reproduced from `signal-exit` (`LICENSE.txt`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
The ISC License

Copyright (c) 2015, Contributors

Permission to use, copy, modify, and/or distribute this software
for any purpose with or without fee is hereby granted, provided
that the above copyright notice and this permission notice
appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE
LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES
OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

### BSD-2-Clause

The text below is reproduced from `esprima` (`LICENSE.BSD`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
Copyright JS Foundation and other contributors, https://js.foundation/

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

  * Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
  * Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### BSD-3-Clause

The text below is reproduced from `diff` (`LICENSE`); the copyright/attribution
notice that applies to each package is listed in the tables above.

```
BSD 3-Clause License

Copyright (c) 2009-2015, Kevin Decker <kpdecker@gmail.com>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### Apache-2.0

The `siada-cli-ui` bundle includes Apache-2.0 licensed code (`@agentclientprotocol/sdk`, and the Apache-2.0 banner of `@jrichman/ink`). The full Apache License 2.0 text is distributed with Siada CLI as the repository `LICENSE` file (in wheels: `.dist-info/licenses/LICENSE`) and is available at https://www.apache.org/licenses/LICENSE-2.0


## Additional license texts

Some packages ship a LICENSE file whose text differs from the standard license
bodies reproduced above (extra attribution text, different wording, or a
different list style). Those files are reproduced in full:

### `commander` (`LICENSE`)

```
(The MIT License)

Copyright (c) 2011 TJ Holowaychuk <tj@vision-media.ca>

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

### `devlop` (`license`)

```
(The MIT License)

Copyright (c) 2023 Titus Wormer <tituswormer@gmail.com>

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

### `es-toolkit` (`LICENSE`)

```
MIT License

Copyright (c) 2024 Viva Republica, Inc

Copyright OpenJS Foundation and other contributors

Parts of the test suite and compatibility layer in `es-toolkit/compat` are derived from Lodash (https://github.com/lodash/lodash) by the OpenJS Foundation (https://openjsf.org/) and Underscore.js by Jeremy Ashkenas, DocumentCloud and Investigative Reporters & Editors (http://underscorejs.org/)

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

### `highlight.js` (`LICENSE`)

```
BSD 3-Clause License

Copyright (c) 2006, Ivan Sagalaev.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### `lowlight` (`license`)

```
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

### `marked` (`LICENSE.md`)

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

## Notes

* `type-fest` is dual-licensed `(MIT OR CC0-1.0)`; the MIT option is the one
  reproduced above.
* `yoga-layout` is the only bundled package without a published LICENSE file.
  Its `dist/src/index.js`, `dist/src/wrapAssembly.js`, and
  `dist/src/generated/YGEnums.js` headers state the MIT license and
  `Copyright (c) Meta Platforms, Inc. and affiliates.`; that attribution is
  preserved above together with the MIT text in this file.
* `ink-markdown` (additional attribution) declares MIT in `package.json` but
  its published tarball has no LICENSE file. Its package author is recorded
  as the available attribution.
* `@jrichman/ink` is MIT (per `package.json` and its license file), but the
  three files it contributes to the bundle (`build/scroll.js`, `build/layout.js`,
  `build/selection.js`) carry `Copyright 2025 Google LLC` /
  `SPDX-License-Identifier: Apache-2.0` banners, which esbuild preserves in the
  bundle's `@license` block.
* The only `esbuild-meta.json` input that is not a file of an installed package
  or of `siada_cli_ui/src/` is esbuild's virtual `devtools-stub` module, which
  replaces Ink's optional `react-devtools-core` import (`react-devtools-core`
  itself is not bundled); no bundled input was left without an owning package.
* `escape-string-regexp@4.0.0` is kept in the second table only because it is
  recorded in `package-lock.json` (it comes from the `eslint` dev tree and is
  not reachable from the runtime dependencies).
* `fsevents` is kept external by the bundle configuration (native macOS
  watcher); it is not included in `siada-ui.js`.