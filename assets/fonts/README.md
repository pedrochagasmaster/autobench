# Bundled fonts

These TrueType fonts are used (and embedded) by
`scripts/build_autobench_pptx.py` so the generated deck renders identically on
any machine. All are redistributable under their respective open licenses.

| File(s) | Family | License | Source |
|---------|--------|---------|--------|
| `Inter-*.ttf`, `InterDisplay-*.ttf` | Inter / Inter Display | SIL Open Font License 1.1 | https://github.com/rsms/inter |
| `JetBrainsMono-*.ttf` | JetBrains Mono | SIL Open Font License 1.1 | https://github.com/JetBrains/JetBrainsMono |
| `FontAwesome6Free-Solid.ttf` | Font Awesome 6 Free (Solid) | SIL Open Font License 1.1 | https://github.com/FortAwesome/Font-Awesome |

Notes:

- `FontAwesome6Free-Solid.ttf` was converted from the upstream OTF (CFF) to TTF
  (glyf) outlines so it embeds cleanly via the OOXML `fntdata` mechanism; only
  the SIL OFL-licensed icon font is affected (Font Awesome's CSS/JS, under
  MIT, is not bundled).
- Inter / Inter Display use the Mark-like humanist sans as a portable stand-in
  for Mastercard's proprietary "Mark" typeface.
