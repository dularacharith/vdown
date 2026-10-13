package com.vdown.app.engine;

import android.text.Html;
import com.vdown.app.data.MediaFormat;
import com.vdown.app.data.MediaInfo;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class FacebookResolver {
    private final OkHttpClient client;

    public FacebookResolver() {
        this.client = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .followRedirects(true)
                .build();
    }

    public static boolean isFacebookUrl(String url) {
        if (url == null) return false;
        String lower = url.toLowerCase();
        return lower.contains("facebook.com")
                || lower.contains("fb.watch")
                || lower.contains("fb.gg")
                || lower.contains("m.facebook.com")
                || lower.contains("web.facebook.com");
    }

    public String normalizeFacebookUrl(String url) {
        if (url == null) return null;
        String cleanUrl = url.trim().replaceAll("^['\"]|['\"]$", "");

        // 1. Expand /share/r/<token> into standard reel URL
        Matcher reelMatcher = Pattern.compile("facebook\\.com/share/r/([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(cleanUrl);
        if (reelMatcher.find()) {
            String token = reelMatcher.group(1);
            if (token.matches("\\d+")) {
                return "https://www.facebook.com/reel/" + token + "/";
            }
        }

        // 2. Expand /share/v/<token> into standard watch URL
        Matcher videoMatcher = Pattern.compile("facebook\\.com/share/v/([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(cleanUrl);
        if (videoMatcher.find()) {
            String token = videoMatcher.group(1);
            if (token.matches("\\d+")) {
                return "https://www.facebook.com/watch/?v=" + token;
            }
        }

        // 3. For shortlinks like fb.watch or alphanumeric share links, follow redirects
        if (cleanUrl.toLowerCase().contains("fb.watch")
                || cleanUrl.toLowerCase().contains("/share/r/")
                || cleanUrl.toLowerCase().contains("/share/v/")) {
            try {
                Request headReq = new Request.Builder()
                        .url(cleanUrl)
                        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
                        .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                        .header("Accept-Language", "en-US,en;q=0.9")
                        .header("Sec-Fetch-Mode", "navigate")
                        .build();
                try (Response resp = client.newCall(headReq).execute()) {
                    String finalUrl = resp.request().url().toString();
                    if (finalUrl != null && !finalUrl.isEmpty()) {
                        Matcher rm = Pattern.compile("/reel/([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(finalUrl);
                        if (rm.find()) {
                            return "https://www.facebook.com/reel/" + rm.group(1) + "/";
                        }
                        Matcher vm = Pattern.compile("[?&]v=([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(finalUrl);
                        if (vm.find()) {
                            return "https://www.facebook.com/watch/?v=" + vm.group(1);
                        }
                        Matcher storyMatcher = Pattern.compile("story_fbid=([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(finalUrl);
                        if (storyMatcher.find()) {
                            return "https://www.facebook.com/watch/?v=" + storyMatcher.group(1);
                        }
                        return finalUrl;
                    }
                }
            } catch (Exception ignored) {
            }
        }

        return cleanUrl;
    }

    public MediaInfo resolve(String rawUrl) throws IOException {
        String normalizedUrl = normalizeFacebookUrl(rawUrl);
        if (normalizedUrl == null) {
            throw new IOException("Invalid Facebook URL");
        }

        List<String> pageVariants = new ArrayList<>();

        // Extract ID if present (numeric or alphanumeric)
        String extractedId = null;
        Matcher reelIdMatcher = Pattern.compile("reel/([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(normalizedUrl);
        if (reelIdMatcher.find()) {
            extractedId = reelIdMatcher.group(1);
        } else {
            Matcher vMatcher = Pattern.compile("[?&]v=([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(normalizedUrl);
            if (vMatcher.find()) {
                extractedId = vMatcher.group(1);
            } else {
                Matcher storyMatcher = Pattern.compile("story_fbid=([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(normalizedUrl);
                if (storyMatcher.find()) {
                    extractedId = storyMatcher.group(1);
                } else {
                    Matcher shareReelMatcher = Pattern.compile("share/r/([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(normalizedUrl);
                    if (shareReelMatcher.find()) {
                        extractedId = shareReelMatcher.group(1);
                    } else {
                        Matcher shareVidMatcher = Pattern.compile("share/v/([a-zA-Z0-9_-]+)", Pattern.CASE_INSENSITIVE).matcher(normalizedUrl);
                        if (shareVidMatcher.find()) {
                            extractedId = shareVidMatcher.group(1);
                        }
                    }
                }
            }
        }

        if (extractedId != null) {
            pageVariants.add("https://m.facebook.com/watch/?v=" + extractedId + "&_rdr");
            pageVariants.add("https://www.facebook.com/reel/" + extractedId + "/");
            pageVariants.add("https://www.facebook.com/watch/?v=" + extractedId);
            pageVariants.add("https://m.facebook.com/story.php?story_fbid=" + extractedId);
            pageVariants.add("https://m.facebook.com/share/r/" + extractedId + "/");
        }
        pageVariants.add(normalizedUrl);
        if (!normalizedUrl.equals(rawUrl)) {
            pageVariants.add(rawUrl);
        }

        String[] userAgents = new String[]{
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"
        };

        for (String targetPageUrl : pageVariants) {
            for (String ua : userAgents) {
                try {
                    Request request = new Request.Builder()
                            .url(targetPageUrl)
                            .header("User-Agent", ua)
                            .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
                            .header("Accept-Language", "en-US,en;q=0.9")
                            .header("Sec-Fetch-Dest", "document")
                            .header("Sec-Fetch-Mode", "navigate")
                            .header("Sec-Fetch-Site", "none")
                            .header("Upgrade-Insecure-Requests", "1")
                            .build();

                    String html;
                    try (Response response = client.newCall(request).execute()) {
                        if (response.body() == null) {
                            continue;
                        }
                        html = response.body().string();
                    }

                    if (html == null || html.isEmpty()) {
                        continue;
                    }

                    String hdUrl = extractMatch(html,
                            "\"browser_native_hd_url\"\\s*:\\s*\"([^\"]+)\"",
                            "\"playable_url_quality_hd\"\\s*:\\s*\"([^\"]+)\"",
                            "hd_src\\s*:\\s*\"([^\"]+)\"",
                            "\"hd_src_no_ratelimit\"\\s*:\\s*\"([^\"]+)\""
                    );

                    String sdUrl = extractMatch(html,
                            "\"browser_native_sd_url\"\\s*:\\s*\"([^\"]+)\"",
                            "\"playable_url\"\\s*:\\s*\"([^\"]+)\"",
                            "sd_src\\s*:\\s*\"([^\"]+)\"",
                            "\"sd_src_no_ratelimit\"\\s*:\\s*\"([^\"]+)\""
                    );

                    if (hdUrl == null && sdUrl == null) {
                        // Try fallback og:video
                        String ogVideo = extractMatch(html,
                                "<meta\\s+(?:property|name)=[\"'](?:og:video|og:video:url|og:video:secure_url|twitter:player:stream)[\"']\\s+content=[\"']([^\"']+)[\"']",
                                "\"video_url\"\\s*:\\s*\"([^\"]+)\""
                        );
                        if (ogVideo != null && ogVideo.startsWith("http")) {
                            sdUrl = ogVideo;
                        }
                    }

                    if (hdUrl == null && sdUrl == null) {
                        // Try matching direct fbcdn video link
                        String fbcdnVideo = extractMatch(html,
                                "(https?:\\\\/\\\\/[a-zA-Z0-9.-]*fbcdn\\.net\\\\/[^\"'\\s]+\\.mp4[^\"'\\s]*)",
                                "(https?://[a-zA-Z0-9.-]*fbcdn\\.net/[^\"'\\s]+\\.mp4[^\"'\\s]*)"
                        );
                        if (fbcdnVideo != null) {
                            sdUrl = fbcdnVideo;
                        }
                    }

                    if (hdUrl == null && sdUrl == null) {
                        continue;
                    }

                hdUrl = decodeJsonUrl(hdUrl);
                sdUrl = decodeJsonUrl(sdUrl);

                // Extract Title
                String rawTitle = extractMatch(html,
                        "<meta\\s+(?:property|name)=[\"']og:title[\"']\\s+content=[\"']([^\"']+)[\"']"
                );
                String title = "Facebook Video";
                if (rawTitle != null && !rawTitle.trim().isEmpty()) {
                    try {
                        title = Html.fromHtml(rawTitle, Html.FROM_HTML_MODE_LEGACY).toString().trim();
                    } catch (Exception e) {
                        title = rawTitle.replace("&amp;", "&").replace("&quot;", "\"").replace("&#039;", "'").trim();
                    }
                }

                // Extract Thumbnail
                String thumbnail = extractMatch(html,
                        "<meta\\s+(?:property|name)=[\"']og:image[\"']\\s+content=[\"']([^\"']+)[\"']"
                );

                MediaInfo info = new MediaInfo();
                info.setId("fb_" + Math.abs(normalizedUrl.hashCode()));
                info.setUrl(normalizedUrl);
                info.setPlatform("Facebook");
                info.setTitle(title);
                info.setAuthor("Facebook");
                if (thumbnail != null) {
                    info.setThumbnailUrl(thumbnail);
                }

                String primaryStreamUrl = (hdUrl != null) ? hdUrl : sdUrl;

                if (hdUrl != null) {
                    MediaFormat hdFormat = new MediaFormat("hd", "HD Video (720p/1080p)", "mp4", hdUrl, false);
                    hdFormat.setQualityHeight(1080);
                    info.addVideoFormat(hdFormat);
                }

                if (sdUrl != null) {
                    MediaFormat sdFormat = new MediaFormat("sd", "SD Video (Standard)", "mp4", sdUrl, false);
                    sdFormat.setQualityHeight(720);
                    info.addVideoFormat(sdFormat);
                }

                // Audio soundtrack format
                if (primaryStreamUrl != null) {
                    MediaFormat audioFormat = new MediaFormat("audio", "Audio Soundtrack (MP3)", "mp3", primaryStreamUrl, true);
                    audioFormat.setAudioBitrateKbps(320);
                    info.addAudioFormat(audioFormat);
                }

                return info;

                } catch (Exception ignored) {
                }
            }
        }

        throw new IOException("Unable to extract Facebook video. The content may be private or protected.");
    }

    private String extractMatch(String text, String... regexes) {
        for (String regex : regexes) {
            Matcher m = Pattern.compile(regex, Pattern.CASE_INSENSITIVE).matcher(text);
            if (m.find()) {
                return m.group(1);
            }
        }
        return null;
    }

    private String decodeJsonUrl(String url) {
        if (url == null) return null;
        return url.replace("\\/", "/")
                .replace("\\u0026", "&")
                .replace("&amp;", "&");
    }
}
