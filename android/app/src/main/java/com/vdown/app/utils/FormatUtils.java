package com.vdown.app.utils;

import java.util.Locale;

public class FormatUtils {

    public static String formatBytes(long bytes) {
        if (bytes <= 0) return "0 B";
        final String[] units = new String[]{"B", "KB", "MB", "GB", "TB"};
        int digitGroups = (int) (Math.log10(bytes) / Math.log10(1024));
        if (digitGroups >= units.length) digitGroups = units.length - 1;
        return String.format(Locale.US, "%.1f %s", bytes / Math.pow(1024, digitGroups), units[digitGroups]);
    }

    public static String formatSpeed(double bytesPerSec) {
        if (bytesPerSec <= 0) return "0 KB/s";
        if (bytesPerSec >= 1024 * 1024) {
            return String.format(Locale.US, "%.1f MB/s", bytesPerSec / (1024 * 1024));
        } else {
            return String.format(Locale.US, "%.0f KB/s", bytesPerSec / 1024);
        }
    }

    public static String formatDuration(long seconds) {
        if (seconds <= 0) return "--:--";
        long h = seconds / 3600;
        long m = (seconds % 3600) / 60;
        long s = seconds % 60;
        if (h > 0) {
            return String.format(Locale.US, "%02d:%02d:%02d", h, m, s);
        } else {
            return String.format(Locale.US, "%02d:%02d", m, s);
        }
    }

    public static String formatEta(long seconds) {
        if (seconds <= 0) return "calculating…";
        if (seconds < 60) {
            return seconds + "s";
        } else if (seconds < 3600) {
            return (seconds / 60) + "m " + (seconds % 60) + "s";
        } else {
            return (seconds / 3600) + "h " + ((seconds % 3600) / 60) + "m";
        }
    }

    public static String sanitizeFilename(String name) {
        if (name == null || name.trim().isEmpty()) {
            return "download_" + System.currentTimeMillis();
        }
        String clean = name.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        if (clean.length() > 100) {
            clean = clean.substring(0, 100);
        }
        return clean;
    }
}
