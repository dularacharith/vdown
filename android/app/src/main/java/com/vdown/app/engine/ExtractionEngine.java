package com.vdown.app.engine;

import com.vdown.app.data.MediaInfo;
import java.io.IOException;

public class ExtractionEngine {
    private final TikTokResolver tikTokResolver;
    private final FacebookResolver facebookResolver;
    private final DirectMediaResolver directMediaResolver;
    private final UniversalResolver universalResolver;
    private final WebpageScraperResolver webpageScraperResolver;

    public ExtractionEngine() {
        this.tikTokResolver = new TikTokResolver();
        this.facebookResolver = new FacebookResolver();
        this.directMediaResolver = new DirectMediaResolver();
        this.universalResolver = new UniversalResolver();
        this.webpageScraperResolver = new WebpageScraperResolver();
    }

    public MediaInfo extract(String url) throws Exception {
        if (url == null || url.trim().isEmpty()) {
            throw new IllegalArgumentException("URL cannot be empty");
        }
        String cleanUrl = url.trim();

        // 1. TikTok Engine (dedicated watermark-free extraction)
        if (TikTokResolver.isTikTokUrl(cleanUrl)) {
            try {
                return tikTokResolver.resolve(cleanUrl);
            } catch (Exception eTikTok) {
                try {
                    return universalResolver.resolve(cleanUrl);
                } catch (Exception ignored) {}
                throw new IOException("Unable to extract TikTok video: " + eTikTok.getMessage());
            }
        }

        // 2. Facebook Engine (dedicated reels, videos, and share links)
        if (FacebookResolver.isFacebookUrl(cleanUrl)) {
            try {
                return facebookResolver.resolve(cleanUrl);
            } catch (Exception eFacebook) {
                try {
                    return universalResolver.resolve(cleanUrl);
                } catch (Exception ignored) {}
                throw new IOException("Unable to extract Facebook video: " + eFacebook.getMessage());
            }
        }

        // 3. Direct Media Engine (only for genuine media files)
        if (DirectMediaResolver.isDirectMediaUrl(cleanUrl)) {
            try {
                return directMediaResolver.resolve(cleanUrl);
            } catch (Exception ignored) {}
        }

        // 4. Universal Resolver (YouTube, Instagram, Twitter/X, Reddit, etc.)
        try {
            return universalResolver.resolve(cleanUrl);
        } catch (Exception eUniversal) {
            // Never fall through to direct media probe if domain is social media
            if (isSocialMediaDomain(cleanUrl)) {
                throw new IOException("Unable to extract media: " + eUniversal.getMessage());
            }

            // 5. Webpage Scraper Engine fallback
            try {
                return webpageScraperResolver.resolve(cleanUrl);
            } catch (Exception eScraper) {
                // If webpage scraper also fails, try direct media probe as last resort
                try {
                    return directMediaResolver.resolve(cleanUrl);
                } catch (Exception eDirect) {
                    throw new IOException("Unable to extract media: " + eUniversal.getMessage());
                }
            }
        }
    }

    private boolean isSocialMediaDomain(String url) {
        if (url == null) return false;
        String lower = url.toLowerCase();
        return lower.contains("facebook.com") || lower.contains("fb.watch") || lower.contains("fb.gg")
                || lower.contains("tiktok.com") || lower.contains("instagram.com")
                || lower.contains("youtube.com") || lower.contains("youtu.be")
                || lower.contains("twitter.com") || lower.contains("x.com");
    }
}
