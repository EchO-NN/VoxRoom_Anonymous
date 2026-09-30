# Project website

The static website is in `site/`. The root `index.html` opens that page.
Images, videos, scripts, and fonts use local paths.

## Preview

From the repository root:

```bash
python -m http.server 8000
```

Open `http://localhost:8000/site/`. The site also opens directly from
`site/index.html`. The overview includes audio and embedded English subtitles;
the short simulation video is silent. Both MP4 and WebM files are included.

Charts and tables contain the results reported in the paper. Update them when
the corresponding paper tables change.

## Anonymous GitHub

Push the prepared review branch to GitHub, then open
[Anonymous GitHub](https://anonymous.4open.science/anonymize). Select that branch
and its final commit. Leave **Auto-update from GitHub** off to keep the submitted
version fixed. Use an ID without author information, add identifying names to
**Terms to redact**, and set **Remove when expired** to a date after review.

For the website, first set the source repository's GitHub Pages source to
**Deploy from a branch**, choose the same review branch, and select **/ (root)**.
Then enable **GitHub Pages** in the anonymization form. The project page will
be at `https://anonymous.4open.science/w/<ID>/site/`; the code browser will be at
`https://anonymous.4open.science/r/<ID>/`. Replace `<ID>` with the ID returned by
the service before adding either link to the submission.

The [official form](https://github.com/tdurieux/anonymous_github/blob/main/public/partials/anonymize.htm)
requires the Pages and anonymized repository branches to match. The
[website handler](https://github.com/tdurieux/anonymous_github/blob/main/src/server/routes/webview.ts)
serves the committed HTML and assets directly.

Before submitting, open the generated links in a private browser window and
check video playback, figures, and the source link. On Anonymous GitHub, the
website's source buttons open the matching code browser, where reviewers can
download the repository ZIP. In a local or GitHub preview they open the README.
Local release archives are built separately in `dist/`.
