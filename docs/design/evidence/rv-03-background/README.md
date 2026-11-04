# RV-03 background scientific/render proof evidence

Measured 2026-11-04 on the `review-rv03-audio-and-spectrograms` working tree from
reviewed RV-02 integration baseline `0cae437`. This is **background/offscreen source-app
evidence**, not visible Cocoa, installed macOS, Windows, a physical audio-device check, or
owner approval of real field-call readability.

## Numeric reference and input cohort

- Python 3.12.7, NumPy 2.5.4, PySide6/Qt 6.11.2; macOS 26.6.2 arm64, Apple M2,
  16 GiB RAM.
- The unit reference is the independent R expression
  `0.5 - 0.5*cos(2*pi*(0:7)/7)` followed by one-sided `Mod(fft(x*w))^2`. The five
  checked powers are `0.022791599075738`, `1.08235420046213`, `3.0625`,
  `1.08235420046213`, `0.022791599075738`, with Python tolerance `1e-12`.
- The timing cohort is all 20 repository-bundled prototype clips: synthesized, 6 seconds,
  mono PCM16 at 16 kHz. It contains no genuine research recording. Aggregate SHA-256 over
  the sorted `shasum -a 256 assets/clip-*.wav` lines is
  `447068e401ed02bd7a6d02dedd3ef5b239fb53a1a39727201d71b23dcc0bd264`.
- Default settings were 4.2 kHz ceiling, Balanced symmetric-Hann window, 50% overlap,
  zero-Hz floor, 50 dB peak-relative contrast and Magma. Each clip used its full available
  context around a centred 0.5-second candidate. Every row was a distinct clip and a fresh
  render; repetitions per tier: 20.

## Observations

| Operation | P10 | P50 | P90 | In-memory raster bytes |
|---|---:|---:|---:|---:|
| 320×120 thumbnail calculation + RGB mapping | 5.206 ms | 5.392 ms | 6.201 ms | 268,800 |
| 1200×450 detail calculation + RGB mapping | 26.508 ms | 27.276 ms | 28.978 ms | 3,780,000 |
| Qt detail paint at DPR 1.0 | 0.664 ms | 0.720 ms | 0.785 ms | not serialized |
| Qt detail paint at DPR 1.5 | 1.246 ms | 1.398 ms | 1.709 ms | not serialized |
| Qt detail paint at DPR 2.0 | 1.269 ms | 1.331 ms | 1.744 ms | not serialized |

The byte column is exact transient RGB plus float32 relative-dB storage, not a PNG/cache
forecast. RV-04 still owns codec bytes, cache staging, calibrated storage estimates, worker
concurrency and 1k/50k scheduling. These synthetic timings are not production constants or a
time promise.

## Remaining owner gate

The repository has no consented genuine field-call cohort or approved R artifact archive.
Visible native playback on a physical device and scientific screenshot review also require an
owner-attended run. Accordingly, real-call readability, physical-device failure behavior,
visible 100–200% Cocoa review, cross-platform multimedia, PNG/cache sizes and calibrated
large-batch estimates remain **blocked/deferred evidence**, not inferred passes.
