package com.vdown.app.engine;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.vdown.app.data.MediaFormat;
import com.vdown.app.data.MediaInfo;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class UniversalResolver {
    private static final String[] COBALT_INSTANCES = new String[]{
            "https://api.cobalt.tools/",
            "https://cobalt-api.kwiatekm.tokyo/",
            "https://api.server.cobalt.tools/"
    };

    private final OkHttpClient client;

    public UniversalResolver() {
        this.client = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(25, TimeUnit.SECONDS)
                .build();
    }

    public static String detectPlatform(String url) {
        if (url == null) return "Web";
        String lower = url.toLowerCase();
        if (lower.contains("youtube.com") || lower.contains("youtu.be")) return "YouTube";
        if (lower.contains("instagram.com")) return "Instagram";
        if (lower.contains("facebook.com") || lower.contains("fb.watch")) return "Facebook";
        if (lower.contains("twitter.com") || lower.contains("x.com")) return "X / Twitter";
        if (lower.contains("reddit.com")) return "Reddit";
        if (lower.contains("vimeo.com")) return "Vimeo";
        if (lower.contains("twitch.tv")) return "Twitch";
        return "Universal Stream";
    }

    public MediaInfo resolve(String url) throws IOException {
        String platform = detectPlatform(url);
        Exception lastError = null;

        for (String instance : COBALT_INSTANCES) {
            try {
                return tryCobaltInstance(instance, url, platform);
            } catch (Exception e) {
                lastError = e;
            }
        }

        throw new IOException("Failed to resolve media stream: " + (lastError != null ? lastError.getMessage() : "Unknown error"));
    }

    private MediaInfo tryCobaltInstance(String apiUrl, String url, String platform) throws IOException {
        JsonObject payload = new JsonObject();
        payload.addProperty("url", url);
        payload.addProperty("videoQuality", "1080");

        RequestBody body = RequestBody.create(
                payload.toString(),
                MediaType.parse("application/json; charset=utf-8")
        );

        Request request = new Request.Builder()
                .url(apiUrl)
                .post(body)
                .header("Accept", "application/json")
                .header("Content-Type", "application/json")
                .header("User-Agent", "vdown-android/1.0.0")
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful() || response.body() == null) {
                throw new IOException("HTTP " + response.code() + " from " + apiUrl);
            }

            String respStr = response.body().string();
            JsonObject root = JsonParser.parseString(respStr).getAsJsonObject();

            String status = root.has("status") ? root.get("status").getAsString() : "";
            if ("error".equalsIgnoreCase(status)) {
                String errorMsg = root.has("text") ? root.get("text").getAsString() : "Error from resolver";
                throw new IOException(errorMsg);
            }

            MediaInfo info = new MediaInfo();
            info.setId("media_" + System.currentTimeMillis());
            info.setUrl(url);
            info.setPlatform(platform);

            String title = platform + " Media";
            if (root.has("filename")) {
                title = root.get("filename").getAsString();
                if (title.contains(".")) {
                    title = title.substring(0, title.lastIndexOf('.'));
                }
            }
            info.setTitle(title);
            info.setAuthor(platform + " Creator");

            if (root.has("url")) {
                String streamUrl = root.get("url").getAsString();
                // Add Best / 1080p format
                MediaFormat fBest = new MediaFormat("best", "Best Quality (HD)", "mp4", streamUrl, false);
                fBest.setQualityHeight(1080);
                info.addVideoFormat(fBest);

                // Add 720p format
                MediaFormat f720 = new MediaFormat("720p", "720p Standard", "mp4", streamUrl, false);
                f720.setQualityHeight(720);
                info.addVideoFormat(f720);

                // Audio extraction format
                MediaFormat fAudio = new MediaFormat("audio_320", "Extract Audio (MP3 320 kbps)", "mp3", streamUrl, true);
                fAudio.setAudioBitrateKbps(320);
                info.addAudioFormat(fAudio);

                MediaFormat fFlac = new MediaFormat("audio_flac", "Lossless Audio (FLAC)", "flac", streamUrl, true);
                info.addAudioFormat(fFlac);
            } else if (root.has("picker") && root.get("picker").isJsonArray()) {
                // Photo post or multiple items
                var picker = root.getAsJsonArray("picker");
                for (int i = 0; i < picker.size(); i++) {
                    JsonObject item = picker.get(i).getAsJsonObject();
                    if (item.has("url")) {
                        String itemUrl = item.get("url").getAsString();
                        String type = item.has("type") ? item.get("type").getAsString() : "video";
                        boolean isPhoto = "photo".equalsIgnoreCase(type);
                        MediaFormat format = new MediaFormat(
                                "item_" + i,
                                (isPhoto ? "Photo " : "Video ") + (i + 1),
                                isPhoto ? "jpg" : "mp4",
                                itemUrl,
                                false
                        );
                        info.addVideoFormat(format);
                    }
                }
            }

            return info;
        }
    }
}
