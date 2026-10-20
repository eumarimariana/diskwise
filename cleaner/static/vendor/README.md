# Bundled libraries

Local copies so the interface works without internet. Don't edit these files by hand.

| File | Project | Version | License |
|---|---|---|---|
| `tailwind.js` | [Tailwind CSS](https://tailwindcss.com) (Play CDN) | 3.4.16 | MIT |
| `chart.umd.min.js` | [Chart.js](https://www.chartjs.org) | 4.4.1 | MIT |
| `lucide.min.js` | [Lucide](https://lucide.dev) | 0.460.0 | ISC |
| `inter-*.woff2` | [Inter](https://rsms.me/inter/) via Fontsource | 5.1.0 | SIL OFL 1.1 |

To update, download the new version from the same addresses:

```bash
curl -L -o tailwind.js https://cdn.tailwindcss.com/3.4.16
curl -L -o chart.umd.min.js https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js
curl -L -o lucide.min.js https://unpkg.com/lucide@0.460.0/dist/umd/lucide.min.js
curl -L -o inter-latin-wght-normal.woff2 https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.1.0/files/inter-latin-wght-normal.woff2
curl -L -o inter-latin-ext-wght-normal.woff2 https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.1.0/files/inter-latin-ext-wght-normal.woff2
```
