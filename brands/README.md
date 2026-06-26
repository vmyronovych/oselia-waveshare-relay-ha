# Brand assets (for the Home Assistant brands repo)

These PNGs fix the **device-page / integrations-list logo** for the `waveshare_relay`
custom integration. HA loads integration brand images from the central
`https://brands.home-assistant.io` CDN, not from a local integration — so until these
are merged there, HA shows a broken-image placeholder for the `waveshare_relay` domain.
There is **no local override**; submitting these is the only way to get the logo on the
device page.

Expected files (transparent background; icons must be square):

```
custom_integrations/waveshare_relay/
  icon.png      256x256
  icon@2x.png   512x512
  logo.png      (full lockup)
  logo@2x.png
```

## Submitting

1. Fork `home-assistant/brands`.
2. Copy this `custom_integrations/waveshare_relay/` folder into the repo root's
   `custom_integrations/`.
3. Open a PR. CI checks sizes/transparency.
4. Once merged, HA shows the logo on the device page and integrations list — no
   integration change needed.

> The brand is **Waveshare's**, not OSELIA's. Use Waveshare's product/brand mark (or a
> neutral relay icon), not the OSELIA logo, for these assets.
