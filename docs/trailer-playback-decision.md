# Trailer playback decision

`vault-api` enriches item details with `trailer_url` when TMDB has a YouTube
trailer for the title. The tvOS app now uses that field only as an availability
hint: the actual playback URL is resolved just-in-time through
`GET /library/item/{item_id}/trailer-stream`.

## Chosen path

The endpoint uses `yt-dlp` server-side and prefers a combined progressive MP4
format (YouTube itag `22` or `18`, H.264/AAC) before falling back to another
combined MP4 or HLS (`m3u8`). The returned DTO is StreamInfo-compatible:
`{ "url": "...", "container": "mp4|hls" }`.

For this change the API returns the progressive/HLS URL directly. That keeps the
existing Apple TV AVPlayer pipeline simple and avoids making `vault-api` a
high-bandwidth relay for trailer playback. The resolver caches the short-lived
CDN URL for roughly one hour because YouTube media URLs expire.

## IP binding caveat

YouTube CDN URLs can be bound to the resolving server's egress IP. If the Apple
TV cannot open direct CDN URLs in a deployment, the robust follow-up is to return
a `vault-api` proxy URL from `/trailer-stream` and have the backend fetch from
YouTube and relay bytes to the app. In either mode `vault-api` needs egress to
YouTube; production network policies must allow that traffic.
