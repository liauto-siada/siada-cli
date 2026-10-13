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