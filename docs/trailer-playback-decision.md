# Trailer playback decision (tvOS)

`vault-api` now enriches item details with `trailer_url` when TMDB has a YouTube
trailer for the title. The tvOS app decodes that field, but intentionally does
not render a **Trailer** button yet.

Reasoning:

- TMDB trailer entries usually point to YouTube watch URLs, not direct media
  streams.
- tvOS playback in this app is AVPlayer-based, and YouTube watch pages cannot be
  played directly with AVPlayer.
- tvOS has no clean in-app equivalent to `SFSafariViewController` for opening a
  web YouTube player inside the app.
- Launching or deep-linking the YouTube tvOS app is not reliable enough for an
  acceptance criterion that says the button should only appear when an actually
  playable path exists.

Decision: keep `trailer_url` available in the API and model for future clients or
for a future explicit handoff flow, but hide the tvOS button until the app owns a
reliable playable route (for example a backend-provided direct stream that is
allowed to be played, or a deliberate external-app handoff UX).
