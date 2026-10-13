package com.vdown.app.engine;

import com.vdown.app.data.MediaFormat;
import com.vdown.app.data.MediaInfo;
import java.io.IOException;
import java.net.URI;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class DirectMediaResolver {
    private final OkHttpClient client;

    public DirectMediaResolver() {
        this.client = new OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(10, TimeUnit.SECONDS)
                .followRedirects(true)
                .build();
    }

    public static boolean isDirectMediaUrl(String url) {
        if (url == null) return false;
        String clean = url.toLowerCase().split("\\?")[0];
        return clean.endsWith(".mp4") || clean.endsWith(".mkv") || clean.endsWith(".webm")
                || clean.endsWith(".mov") || clean.endsWith(".avi") || clean.endsWith(".flv")
                || clean.endsWith(".mp3") || clean.endsWith(".m4a") || clean.endsWith(".flac")
                || clean.endsWith(".wav") || clean.endsWith(".opus") || clean.endsWith(".aac");
    }

    public MediaInfo resolve(String url) throws IOException {
        Request request = new Request.Builder()
                .url(url)
                .head()
                .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                .build();

        long contentLength = -1;
        String contentType = "";

        try (Response response = client.newCall(request).execute()) {
            if (response.isSuccessful()) {
                String clHeader = response.header("Content-Length");
                if (clHeader != null) {
                    try {
                        contentLength = Long.parseLong(clHeader);
                    } catch (NumberFormatException ignored) {}
                }
                contentType = response.header("Content-Type", "");
            }
        } catch (Exception e) {
            // Some servers reject HEAD requests; try GET with Range
            Request getRange = new Request.Builder()
                    .url(url)
                    .header("Range", "bytes=0-1")
                    .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                    .build();
            try (Response response = client.newCall(getRange).execute()) {
                contentType = response.header("Content-Type", "");
            }
        }

        if (contentType != null) {
            String ctLower = contentType.toLowerCase();
            if (ctLower.contains("text/html") || ctLower.contains("text/plain") || ctLower.contains("application/json") || ctLower.contains("application/xhtml+xml")) {
                throw new IOException("URL points to a webpage (" + contentType + "), not a direct media stream.");
            }
        }

        if (!isDirectMediaUrl(url) && (contentType == null || (!contentType.contains("video") && !contentType.contains("audio") && !contentType.contains("octet-stream")))) {
            throw new IOException("Target URL is not a recognized direct media file.");
        }

        String path = "";
        try {
            path = URI.create(url).getPath();
        } catch (Exception ignored) {}

        String filename = "media_download";
        if (path != null && path.contains("/")) {
            filename = path.substring(path.lastIndexOf('/') + 1);
            if (filename.contains(".")) {
                filename = filename.substring(0, filename.lastIndexOf('.'));
            }
        }

        String ext = "mp4";
        boolean isAudio = false;
        if (url.toLowerCase().contains(".mp3") || (contentType != null && contentType.contains("audio/mpeg"))) {
            ext = "mp3";
            isAudio = true;
        } else if (url.toLowerCase().contains(".flac") || (contentType != null && contentType.contains("audio/flac"))) {
            ext = "flac";
            isAudio = true;
        } else if (url.toLowerCase().contains(".m4a") || (contentType != null && contentType.contains("audio/mp4"))) {
            ext = "m4a";
            isAudio = true;
        } else if (url.toLowerCase().contains(".wav") || (contentType != null && contentType.contains("audio/wav"))) {
            ext = "wav";
            isAudio = true;
        }

        MediaInfo info = new MediaInfo();
        info.setId("direct_" + System.currentTimeMillis());
        info.setUrl(url);
        info.setTitle(filename.isEmpty() ? "Direct Media" : filename);
        info.setAuthor("Direct Link");
        info.setPlatform("Direct HTTP");

        MediaFormat format = new MediaFormat("direct", isAudio ? "Direct Audio" : "Direct Video", ext, url, isAudio);
        if (contentLength > 0) {
            format.setEstimatedBytes(contentLength);
        }
        if (isAudio) {
            info.addAudioFormat(format);
        } else {
            info.addVideoFormat(format);
        }

        return info;
    }
}
