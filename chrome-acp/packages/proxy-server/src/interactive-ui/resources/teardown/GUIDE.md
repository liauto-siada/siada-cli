# Teardown in interactive UI

Use this toolkit when you judge a working 3D mechanism useful for the user's
request. Choose the production method yourself. Ordinary HTML and source-based
pages share one interactive UI entry point; there is no user mode selector.

## Present and refine

1. Read the requested mechanism's reference and establish meaningful dimensions.
2. Choose a nearby source example or create small modules for math, geometry,
   stage and controls. Keep the compiled library out of model context.
3. Call `browser_ui_build` to show the working page directly in the current chat.
4. Decide whether targeted edits or `browser_ui_inspect` would resolve a specific
   uncertainty. Reuse existing evidence; inspection is optional.
5. Use Share when the user requests a separate webpage.

The workspace already contains the kit and source examples. Dependencies are
provided by Chrome ACP. Use its build tool rather than installing packages or
running the upstream first-run commands in a generated project.

## Source examples

| Directory | Mechanism | Shared driver and useful modules |
| --- | --- | --- |
| `v8-shared/` | 90-degree cross-plane V8 | Crank angle drives slider-crank pistons, valves and approximate chamber-pressure readouts. `kin.js`, `engine.js`, `stage.js`. |
| `cessna-shared/` | Cessna 337 main landing gear | Stroke drives a rack and pinion and the whole gear pose. `gear.js`, `flight.js`, `stage.js`. |
| `strandbeest-shared/` | Jansen walking linkage | Wind drives the crank; joints follow circle intersections from link lengths. `jansen.js`, `beast.js`, `stage.js`. |

The V8 starter has responsive controls already connected to the state bridge.
Use `./viewer.js` for new controls and adapt the other reference examples to the
available viewport instead of shrinking their original 1600-by-900 consoles.
Import `three`, `three/addons/*` and `teardown-kit/*` from source modules.

## Build a coherent mechanism

- Start from a photo, manual diagram or dimensional reference. Distinguish sourced
  dimensions from approximations.
- Keep math independent of Three.js. One input should determine all poses,
  gauges and charts. Do not animate those quantities independently.
- Open or isolate the part doing the work. Choose a camera that exposes the
  mechanism, and keep important parts and controls inside the viewport.
- Fix collisions with dimensions or geometry. Compare relevant states to the
  reference when uncertain.
- Use a pale studio, readable contours and one accent for the active part.
  Keep labels readable at sidebar width and limit expensive post-processing.
- Warm shaders before interaction. Reuse geometry and materials and suspend
  rendering outside the viewport.

For a deterministic simulation, define `render(t)` from the shared math. Use a
seeded generator at setup and avoid random or accumulated frame state in captures.
Live pages may integrate time, but their inspection states must be reproducible.

## Preserve interaction

Use `siadaUI.registerState({capture, restore})` for small JSON checkpoints such as
camera, selected subsystem, cutaway, disassembly, input values and pause state.
Share and assistant actions capture the latest checkpoint. Persist user actions
instead of each animation frame. `siadaUI.onVisibility(callback)` suspends work.

Every control must change the scene or data. Explicit assistant actions use
`siadaUI.submit()`; they return to the same conversation with the current state.
Keep generated HTML self-contained within the existing opaque sandbox.

## Upstream shader constraints

- Keep `smoothstep` edges ordered; use `1.0 - smoothstep(b, a, x)` when reversing.
- Clamp shader `pow()` bases to avoid NaN pixels through post-processing.
- Apply the same clipping planes to cutaway geometry and GTAO normal materials.
- Use `polygonOffset` for nearly coplanar decals and shadow surfaces.

The source toolkit is MIT licensed by elvarofficial and whaleyxbt. The original
license is included in source projects and generated HTML.