package com.vdown.app.engine;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.vdown.app.data.MediaFormat;
import com.vdown.app.data.MediaInfo;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class TikTokResolver {
    private static final String API_URL = "https://www.tikwm.com/api/";
    private final OkHttpClient client;

    public TikTokResolver() {
        this.client = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .build();
    }

    public static boolean isTikTokUrl(String url) {
        if (url == null) return false;
        String lower = url.toLowerCase();
        return lower.contains("tiktok.com") || lower.contains("vt.tiktok.com")
                || lower.contains("vm.tiktok.com") || lower.contains("tiktokv.com");
    }

    public MediaInfo resolve(String url) throws IOException {
        FormBody body = new FormBody.Builder()
                .add("url", url)
                .add("hd", "1")
                .build();

        Request request = new Request.Builder()
                .url(API_URL)
                .post(body)
                .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128.0.0.0 Mobile Safari/537.36")
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful() || response.body() == null) {
                throw new IOException("HTTP error from TikTok API: " + response.code());
            }

            String respStr = response.body().string();
            JsonObject root = JsonParser.parseString(respStr).getAsJsonObject();
            if (root.get("code").getAsInt() != 0 || !root.has("data")) {
                throw new IOException("TikTok API returned error code");
            }

            JsonObject data = root.getAsJsonObject("data");
            MediaInfo info = new MediaInfo();
            info.setId(data.has("id") ? data.get("id").getAsString() : "tiktok_" + System.currentTimeMillis());
            info.setUrl(url);
            info.setPlatform("TikTok");

            String title = data.has("title") ? data.get("title").getAsString().trim() : "";
            if (title.isEmpty()) title = "TikTok Video";
            info.setTitle(title);

            if (data.has("author") && data.get("author").isJsonObject()) {
                JsonObject authorObj = data.getAsJsonObject("author");
                String author = authorObj.has("nickname") ? authorObj.get("nickname").getAsString() :
                        (authorObj.has("unique_id") ? authorObj.get("unique_id").getAsString() : "TikTok");
                info.setAuthor(author);
            } else {
                info.setAuthor("TikTok Creator");
            }

            if (data.has("cover")) {
                info.setThumbnailUrl(data.get("cover").getAsString());
            }
            if (data.has("duration")) {
                info.setDurationSeconds(data.get("duration").getAsLong());
            }

            // Watermark-free HD video
            if (data.has("hdplay")) {
                MediaFormat hdFormat = new MediaFormat("hd", "HD Video (No Watermark)", "mp4", data.get("hdplay").getAsString(), false);
                hdFormat.setQualityHeight(1080);
                info.addVideoFormat(hdFormat);
            }

            // Standard Watermark-free video
            if (data.has("play")) {
                MediaFormat sdFormat = new MediaFormat("sd", "Video (No Watermark)", "mp4", data.get("play").getAsString(), false);
                sdFormat.setQualityHeight(720);
                info.addVideoFormat(sdFormat);
            }

            // Audio soundtrack
            if (data.has("music")) {
                MediaFormat musicFormat = new MediaFormat("audio", "Original Audio (MP3)", "mp3", data.get("music").getAsString(), true);
                musicFormat.setAudioBitrateKbps(320);
                info.addAudioFormat(musicFormat);
            }

            return info;
        }
    }
}
