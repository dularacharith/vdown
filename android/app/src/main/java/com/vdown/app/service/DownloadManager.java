package com.vdown.app.service;

import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import androidx.core.content.ContextCompat;
import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.vdown.app.data.DownloadItem;
import com.vdown.app.utils.FileUtils;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

public class DownloadManager {
    private static volatile DownloadManager instance;
    private final Context context;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newFixedThreadPool(3);
    private final OkHttpClient httpClient;
    private final Gson gson = new Gson();

    private final List<DownloadItem> activeDownloads = Collections.synchronizedList(new ArrayList<>());
    private final ConcurrentHashMap<String, Future<?>> downloadTasks = new ConcurrentHashMap<>();
    private final List<DownloadListener> listeners = Collections.synchronizedList(new ArrayList<>());

    public interface DownloadListener {
        void onDownloadProgress(DownloadItem item);
        void onDownloadCompleted(DownloadItem item);
        void onDownloadFailed(DownloadItem item, String error);
        void onDownloadListChanged();
    }

    private DownloadManager(Context context) {
        this.context = context.getApplicationContext();
        this.httpClient = new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .followRedirects(true)
                .build();
    }

    public static DownloadManager getInstance(Context context) {
        if (instance == null) {
            synchronized (DownloadManager.class) {
                if (instance == null) {
                    instance = new DownloadManager(context);
                }
            }
        }
        return instance;
    }

    public void init() {
        // Initialization if needed
    }

    public void addListener(DownloadListener listener) {
        if (!listeners.contains(listener)) {
            listeners.add(listener);
        }
    }

    public void removeListener(DownloadListener listener) {
        listeners.remove(listener);
    }

    public List<DownloadItem> getActiveDownloads() {
        return new ArrayList<>(activeDownloads);
    }

    public void startDownload(DownloadItem item) {
        activeDownloads.add(0, item);
        notifyListChanged();

        // Start Foreground Service
        Intent serviceIntent = new Intent(context, DownloadService.class);
        ContextCompat.startForegroundService(context, serviceIntent);

        Future<?> future = executor.submit(() -> runDownloadTask(item));
        downloadTasks.put(item.getId(), future);
    }

    public void cancelDownload(String itemId) {
        Future<?> future = downloadTasks.remove(itemId);
        if (future != null) {
            future.cancel(true);
        }

        DownloadItem found = null;
        for (DownloadItem item : activeDownloads) {
            if (item.getId().equals(itemId)) {
                found = item;
                break;
            }
        }
        if (found != null) {
            found.setStatus(DownloadItem.Status.CANCELED);
            activeDownloads.remove(found);
            notifyListChanged();
        }
    }

    private void runDownloadTask(DownloadItem item) {
        item.setStatus(DownloadItem.Status.DOWNLOADING);
        notifyProgress(item);

        File outputFile = FileUtils.createUniqueFile(item.getTitle(), item.getExtension());
        item.setDestinationPath(outputFile.getAbsolutePath());

        Request request = new Request.Builder()
                .url(item.getDownloadUrl())
                .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
                .build();

        long startTime = System.currentTimeMillis();
        long lastSpeedCalcTime = startTime;
        long bytesSinceLastCalc = 0;

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new Exception("Server returned HTTP " + response.code());
            }

            ResponseBody body = response.body();
            if (body == null) {
                throw new Exception("Empty response body from server");
            }

            long totalBytes = body.contentLength();
            if (totalBytes > 0) {
                item.setTotalBytes(totalBytes);
            }

            try (InputStream in = body.byteStream();
                 FileOutputStream out = new FileOutputStream(outputFile)) {

                byte[] buffer = new byte[32 * 1024]; // 32KB buffer for high throughput
                long totalDownloaded = 0;
                int read;

                while ((read = in.read(buffer)) != -1) {
                    if (Thread.currentThread().isInterrupted()) {
                        outputFile.delete();
                        return;
                    }

                    out.write(buffer, 0, read);
                    totalDownloaded += read;
                    bytesSinceLastCalc += read;

                    long now = System.currentTimeMillis();
                    long elapsedCalc = now - lastSpeedCalcTime;

                    if (elapsedCalc >= 500) { // update speed and UI every 500ms
                        double speed = (bytesSinceLastCalc * 1000.0) / elapsedCalc;
                        item.setSpeedBytesPerSec(speed);

                        if (totalBytes > 0 && speed > 0) {
                            long remainingBytes = Math.max(0, totalBytes - totalDownloaded);
                            item.setEtaSeconds((long) (remainingBytes / speed));
                            int percent = (int) ((totalDownloaded * 100) / totalBytes);
                            item.setProgressPercent(percent);
                        }

                        item.setDownloadedBytes(totalDownloaded);
                        notifyProgress(item);

                        lastSpeedCalcTime = now;
                        bytesSinceLastCalc = 0;
                    }
                }

                out.flush();
            }

            // Audio volume normalization / boost for TikTok and social media videos
            String ext = item.getExtension().toLowerCase();
            if ((ext.equals("mp4") || ext.equals("mkv")) && item.getSourceUrl() != null && item.getSourceUrl().toLowerCase().contains("tiktok")) {
                try {
                    com.vdown.app.utils.AudioGainBooster.boostAudioInVideo(outputFile, 2.2f);
                } catch (Throwable ignored) {}
            }

            // Completed!
            item.setStatus(DownloadItem.Status.COMPLETED);
            item.setProgressPercent(100);
            item.setDownloadedBytes(outputFile.length());
            FileUtils.scanMediaFile(context, outputFile);

            activeDownloads.remove(item);
            downloadTasks.remove(item.getId());

            notifyCompleted(item);
            notifyListChanged();

        } catch (Exception e) {
            if (!Thread.currentThread().isInterrupted()) {
                item.setStatus(DownloadItem.Status.FAILED);
                item.setErrorMessage(e.getMessage());
                activeDownloads.remove(item);
                downloadTasks.remove(item.getId());
                notifyFailed(item, e.getMessage());
                notifyListChanged();
            }
        }
    }

    private void notifyProgress(DownloadItem item) {
        mainHandler.post(() -> {
            for (DownloadListener listener : listeners) {
                listener.onDownloadProgress(item);
            }
        });
    }

    private void notifyCompleted(DownloadItem item) {
        mainHandler.post(() -> {
            for (DownloadListener listener : listeners) {
                listener.onDownloadCompleted(item);
            }
        });
    }

    private void notifyFailed(DownloadItem item, String error) {
        mainHandler.post(() -> {
            for (DownloadListener listener : listeners) {
                listener.onDownloadFailed(item, error);
            }
        });
    }

    private void notifyListChanged() {
        mainHandler.post(() -> {
            for (DownloadListener listener : listeners) {
                listener.onDownloadListChanged();
            }
        });
    }
}
