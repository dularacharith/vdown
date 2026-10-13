package com.vdown.app.utils;

import android.content.Context;
import android.content.Intent;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Environment;
import androidx.core.content.FileProvider;
import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class FileUtils {

    public static File getVDownDirectory() {
        File downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
        File vdownDir = new File(downloadsDir, "vdown");
        if (!vdownDir.exists()) {
            vdownDir.mkdirs();
        }
        return vdownDir;
    }

    public static File createUniqueFile(String baseName, String extension) {
        File dir = getVDownDirectory();
        String safeName = FormatUtils.sanitizeFilename(baseName);
        File target = new File(dir, safeName + "." + extension);
        int counter = 1;
        while (target.exists()) {
            target = new File(dir, safeName + "_" + counter + "." + extension);
            counter++;
        }
        return target;
    }

    public static void scanMediaFile(Context context, File file) {
        if (context == null || file == null || !file.exists()) return;
        MediaScannerConnection.scanFile(
                context.getApplicationContext(),
                new String[]{file.getAbsolutePath()},
                null,
                (path, uri) -> {}
        );
    }

    public static List<File> getLibraryFiles() {
        File dir = getVDownDirectory();
        if (!dir.exists() || !dir.isDirectory()) {
            return new ArrayList<>();
        }
        File[] files = dir.listFiles((d, name) -> {
            String lower = name.toLowerCase();
            return lower.endsWith(".mp4") || lower.endsWith(".mkv") || lower.endsWith(".webm")
                    || lower.endsWith(".mp3") || lower.endsWith(".flac") || lower.endsWith(".m4a")
                    || lower.endsWith(".wav") || lower.endsWith(".opus");
        });
        if (files == null) return new ArrayList<>();
        List<File> fileList = new ArrayList<>(Arrays.asList(files));
        // Sort descending by last modified
        fileList.sort((f1, f2) -> Long.compare(f2.lastModified(), f1.lastModified()));
        return fileList;
    }

    public static Uri getFileUri(Context context, File file) {
        return FileProvider.getUriForFile(
                context,
                context.getPackageName() + ".fileprovider",
                file
        );
    }

    public static void shareFile(Context context, File file) {
        if (context == null || file == null || !file.exists()) return;
        Uri uri = getFileUri(context, file);
        String mimeType = file.getName().toLowerCase().endsWith(".mp3")
                || file.getName().toLowerCase().endsWith(".flac")
                || file.getName().toLowerCase().endsWith(".m4a")
                || file.getName().toLowerCase().endsWith(".wav") ? "audio/*" : "video/*";

        Intent intent = new Intent(Intent.ACTION_SEND);
        intent.setType(mimeType);
        intent.putExtra(Intent.EXTRA_STREAM, uri);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        context.startActivity(Intent.createChooser(intent, "Share media via"));
    }

    public static void openFileWithExternalApp(Context context, File file) {
        if (context == null || file == null || !file.exists()) return;
        Uri uri = getFileUri(context, file);
        String mimeType = file.getName().toLowerCase().endsWith(".mp3")
                || file.getName().toLowerCase().endsWith(".flac")
                || file.getName().toLowerCase().endsWith(".m4a")
                || file.getName().toLowerCase().endsWith(".wav") ? "audio/*" : "video/*";

        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, mimeType);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        context.startActivity(Intent.createChooser(intent, "Open media with"));
    }
}
