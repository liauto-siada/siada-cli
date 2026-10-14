# Showcase website

The static showcase and user guide live in `site/`. GitHub Pages serves them at
<https://liauto-siada.github.io/siada-cli/>.

The Pages source is the root of the `gh-pages` branch. That branch contains only
the website files, including `.nojekyll`; it does not contain the CLI source.

## Preview

From the repository root:

```bash
python -m http.server 8765 --directory site --bind 127.0.0.1
```

Open <http://127.0.0.1:8765/>. The site uses relative links so the same pages work
under GitHub Pages' `/siada-cli/` path.

## Video optimization

The showcase videos use H.264 MP4 for browser compatibility. Keep their original
1920 × 1080 resolution and 60 fps when optimizing them so small UI text and
scrolling remain readable. The current website copies use `libx264`, the `slow`
preset, CRF 20, and `+faststart`.

To make a candidate from an original recording:

```bash
ffmpeg -i original.mp4 -map 0:v:0 -map '0:a?' \
  -c:v libx264 -preset slow -crf 20 -c:a copy \
  -movflags +faststart candidate.mp4
```

This is lossy compression. Compare text, captions, and motion with the original,
check the duration and frame count, and confirm the candidate is smaller before
replacing a file in `site/assets/`. Retain originals separately and use them for
future encodes; repeatedly encoding an optimized copy compounds quality loss.
Faststart moves the MP4 index before the media data to help playback start
earlier, without changing picture quality.

The homepage defers video sources using `data-src`. The hero video starts loading
when its play button is clicked. Other videos receive their source addresses
when they come within 300 pixels of the viewport. Scrolling attaches addresses
without calling `load()`; activating a demo's play button starts loading and
reveals the native controls. All videos retain `preload="none"`, which browsers
treat as a hint.
Browsers without `IntersectionObserver` receive the addresses immediately, with
the same play buttons. If JavaScript is disabled, download links remain
available. Posters load normally.

Playback error messages appear only after loading has been requested and update
when the visitor switches between Chinese and English.

## Publish an update

Review and commit the website changes first. With authorization to publish:

```bash
git subtree split --prefix=site HEAD
git push github <commit-returned-by-subtree-split>:refs/heads/gh-pages
```

Use a normal push. If Git rejects it, inspect the existing `gh-pages` history
before changing the publishing approach.

In the repository's **Settings → Pages**, select **Deploy from a branch**,
`gh-pages`, and `/ (root)`. GitHub runs the Pages build and deployment.

After deployment, check the homepage, all user-guide pages, language switching,
and video playback at the public URL.