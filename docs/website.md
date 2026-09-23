# Website maintenance

The project website is published online with GitHub Pages from the root of the
`gh-pages` branch. The repository's **About** panel links to the live site.

## Local development

The `site/` directory contains the website source. A local server is only needed
when editing or previewing the website:

```bash
python -m http.server 8000 --directory site
```

Open `http://localhost:8000`. All fonts, images, and media are served with the
website; there are no remote embeds or analytics.

Inline playback uses images sampled from the videos at 12 fps. The overview's
original audio is synchronized to those images, including seeking and buffering.
The standard MP4 and WebM versions also include the overview audio. The short
simulation sequence has no audible soundtrack.

The source ZIP contains the media and omits the generated image sheets. Rebuild
those sheets before previewing the website from an extracted ZIP:

```bash
python scripts/build_video_playback.py
```

This requires FFmpeg and Pillow. Commit website changes on `main`, update the
`gh-pages` root with the contents of `site/`, and push both branches. Check the
GitHub Pages deployment completes before verifying the online website.
