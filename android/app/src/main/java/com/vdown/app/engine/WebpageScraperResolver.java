package com.vdown.app.engine;

import com.vdown.app.data.MediaFormat;
import com.vdown.app.data.MediaInfo;
import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class WebpageScraperResolver {
    private final OkHttpClient client;

    public WebpageScraperResolver() {
        this.client = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .followRedirects(true)
                .build();
    }

    public MediaInfo resolve(String pageUrl) throws IOException {
        Request request = new Request.Builder()
                .url(pageUrl)
                .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36")
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .build();

        String html;
        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful() || response.body() == null) {
                throw new IOException("HTTP error from webpage: " + response.code());
            }
            html = response.body().string();
        }

        // 1. Extract Page Title
        String pageTitle = "Webpage Media";
        Matcher titleMatcher = Pattern.compile("<title>(.*?)</title>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL).matcher(html);
        if (titleMatcher.find()) {
            pageTitle = titleMatcher.group(1).trim().replaceAll("\\s+", " ");
        }

        // 2. Extract OpenGraph Video
        List<String> videoCandidates = new ArrayList<>();
        Pattern ogVideoPattern = Pattern.compile("<meta\\s+(?:property|name)=[\"'](?:og:video|og:video:url|og:video:secure_url|twitter:player:stream)[\"']\\s+content=[\"']([^\"']+)[\"']", Pattern.CASE_INSENSITIVE);
        Matcher ogMatcher = ogVideoPattern.matcher(html);
        while (ogMatcher.find()) {
            String candidate = ogMatcher.group(1);
            if (candidate != null && !candidate.isEmpty() && candidate.startsWith("http")) {
                videoCandidates.add(candidate);
            }
        }

        // 3. Extract HTML5 <video src="..."> or <source src="...">
        Pattern videoTagPattern = Pattern.compile("<(?:video|source)[^>]+src=[\"']([^\"']+\\.(?:mp4|webm|m4v|m3u8)[^\"']*)[\"']", Pattern.CASE_INSENSITIVE);
        Matcher videoTagMatcher = videoTagPattern.matcher(html);
        while (videoTagMatcher.find()) {
            String candidate = videoTagMatcher.group(1);
            if (candidate != null && !candidate.isEmpty()) {
                if (candidate.startsWith("//")) {
                    candidate = "https:" + candidate;
                } else if (!candidate.startsWith("http")) {
                    try {
                        candidate = URI.create(pageUrl).resolve(candidate).toString();
                    } catch (Exception ignored) {}
                }
                if (!videoCandidates.contains(candidate)) {
                    videoCandidates.add(candidate);
                }
            }
        }

        if (videoCandidates.isEmpty()) {
            throw new IOException("No video or stream found on this webpage");
        }

        MediaInfo info = new MediaInfo();
        info.setId("scraped_" + System.currentTimeMillis());
        info.setUrl(pageUrl);
        info.setTitle(pageTitle);
        info.setAuthor("Web Embed");
        info.setPlatform("Webpage Scraper");

        for (int i = 0; i < videoCandidates.size(); i++) {
            String vUrl = videoCandidates.get(i);
            String ext = vUrl.contains(".m3u8") ? "m3u8" : "mp4";
            MediaFormat format = new MediaFormat(
                    "stream_" + i,
                    videoCandidates.size() == 1 ? "Video Stream" : "Stream Option " + (i + 1),
                    ext,
                    vUrl,
                    false
            );
            info.addVideoFormat(format);
        }

        return info;
    }
}
