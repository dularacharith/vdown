package com.vdown.app.ui.home;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import com.bumptech.glide.Glide;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.button.MaterialButtonToggleGroup;
import com.google.android.material.card.MaterialCardView;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.textfield.TextInputEditText;
import com.vdown.app.R;
import com.vdown.app.data.DownloadItem;
import com.vdown.app.data.MediaFormat;
import com.vdown.app.data.MediaInfo;
import com.vdown.app.engine.ExtractionEngine;
import com.vdown.app.service.DownloadManager;
import com.vdown.app.ui.MainActivity;
import com.vdown.app.utils.FormatUtils;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HomeFragment extends Fragment {

    private TextInputEditText etUrl;
    private MaterialButton btnPasteUrl, btnClearUrl, btnInspect, btnDownloadMedia, btnClipboardUse;
    private MaterialCardView cardClipboardBanner, cardMediaInfo;
    private TextView tvClipboardText, tvMediaTitle, tvMediaAuthor, tvDuration, tvPlatformBadge;
    private ImageView ivThumbnail;
    private LinearLayout layoutLoading;
    private MaterialButtonToggleGroup toggleType;
    private View scrollVideoQualities, scrollAudioQualities;
    private ChipGroup chipGroupVideo, chipGroupAudio;

    private final ExtractionEngine extractionEngine = new ExtractionEngine();
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private MediaInfo currentMediaInfo;
    private String detectedClipboardUrl;
    private String pendingUrl = null;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_home, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etUrl = view.findViewById(R.id.et_url);
        btnPasteUrl = view.findViewById(R.id.btn_paste_url);
        btnClearUrl = view.findViewById(R.id.btn_clear_url);
        btnInspect = view.findViewById(R.id.btn_inspect);
        btnDownloadMedia = view.findViewById(R.id.btn_download_media);
        btnClipboardUse = view.findViewById(R.id.btn_clipboard_use);

        cardClipboardBanner = view.findViewById(R.id.card_clipboard_banner);
        tvClipboardText = view.findViewById(R.id.tv_clipboard_text);

        cardMediaInfo = view.findViewById(R.id.card_media_info);
        tvMediaTitle = view.findViewById(R.id.tv_media_title);
        tvMediaAuthor = view.findViewById(R.id.tv_media_author);
        tvDuration = view.findViewById(R.id.tv_duration);
        tvPlatformBadge = view.findViewById(R.id.tv_platform_badge);
        ivThumbnail = view.findViewById(R.id.iv_thumbnail);

        layoutLoading = view.findViewById(R.id.layout_loading);
        toggleType = view.findViewById(R.id.toggle_type);
        scrollVideoQualities = view.findViewById(R.id.scroll_video_qualities);
        scrollAudioQualities = view.findViewById(R.id.scroll_audio_qualities);
        chipGroupVideo = view.findViewById(R.id.chip_group_video);
        chipGroupAudio = view.findViewById(R.id.chip_group_audio);

        setupListeners(view);
        if (pendingUrl != null) {
            String urlToInspect = pendingUrl;
            pendingUrl = null;
            etUrl.setText(urlToInspect);
            inspectUrl(urlToInspect);
        } else {
            checkClipboard();
        }
    }

    private void setupListeners(View root) {
        btnPasteUrl.setOnClickListener(v -> pasteFromClipboard());

        btnClearUrl.setOnClickListener(v -> {
            etUrl.setText("");
            cardMediaInfo.setVisibility(View.GONE);
            currentMediaInfo = null;
        });

        btnInspect.setOnClickListener(v -> {
            String url = etUrl.getText() != null ? etUrl.getText().toString().trim() : "";
            if (url.isEmpty()) {
                Toast.makeText(requireContext(), R.string.error_empty_url, Toast.LENGTH_SHORT).show();
                return;
            }
            inspectUrl(url);
        });

        btnClipboardUse.setOnClickListener(v -> {
            if (detectedClipboardUrl != null) {
                etUrl.setText(detectedClipboardUrl);
                cardClipboardBanner.setVisibility(View.GONE);
                inspectUrl(detectedClipboardUrl);
            }
        });

        toggleType.addOnButtonCheckedListener((group, checkedId, isChecked) -> {
            if (!isChecked) return;
            if (checkedId == R.id.btn_toggle_video) {
                scrollVideoQualities.setVisibility(View.VISIBLE);
                scrollAudioQualities.setVisibility(View.GONE);
            } else if (checkedId == R.id.btn_toggle_audio) {
                scrollVideoQualities.setVisibility(View.GONE);
                scrollAudioQualities.setVisibility(View.VISIBLE);
            }
        });

        btnDownloadMedia.setOnClickListener(v -> startDownload());

        View.OnClickListener platformClickListener = v -> {
            if (v instanceof com.google.android.material.chip.Chip) {
                String platform = ((com.google.android.material.chip.Chip) v).getText().toString();
                Toast.makeText(requireContext(), "Paste your " + platform + " link above", Toast.LENGTH_SHORT).show();
                etUrl.requestFocus();
            }
        };

        View py = root.findViewById(R.id.chip_p_youtube);
        View pt = root.findViewById(R.id.chip_p_tiktok);
        View pi = root.findViewById(R.id.chip_p_instagram);
        View pf = root.findViewById(R.id.chip_p_facebook);
        View px = root.findViewById(R.id.chip_p_twitter);
        View pd = root.findViewById(R.id.chip_p_direct);
        if (py != null) py.setOnClickListener(platformClickListener);
        if (pt != null) pt.setOnClickListener(platformClickListener);
        if (pi != null) pi.setOnClickListener(platformClickListener);
        if (pf != null) pf.setOnClickListener(platformClickListener);
        if (px != null) px.setOnClickListener(platformClickListener);
        if (pd != null) pd.setOnClickListener(platformClickListener);
    }

    public void setUrlAndInspect(String url) {
        if (url == null || url.trim().isEmpty()) return;
        String clean = url.trim();
        this.pendingUrl = clean;
        if (etUrl != null) {
            pendingUrl = null;
            etUrl.setText(clean);
            inspectUrl(clean);
        }
    }

    private void pasteFromClipboard() {
        ClipboardManager cm = (ClipboardManager) requireContext().getSystemService(Context.CLIPBOARD_SERVICE);
        if (cm != null && cm.hasPrimaryClip()) {
            ClipData clip = cm.getPrimaryClip();
            if (clip != null && clip.getItemCount() > 0) {
                CharSequence text = clip.getItemAt(0).getText();
                if (text != null) {
                    etUrl.setText(text.toString().trim());
                    Toast.makeText(requireContext(), "Link pasted", Toast.LENGTH_SHORT).show();
                }
            }
        }
    }

    private void checkClipboard() {
        try {
            ClipboardManager cm = (ClipboardManager) requireContext().getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null && cm.hasPrimaryClip()) {
                ClipData clip = cm.getPrimaryClip();
                if (clip != null && clip.getItemCount() > 0) {
                    CharSequence text = clip.getItemAt(0).getText();
                    if (text != null) {
                        String s = text.toString().trim();
                        if (s.startsWith("http://") || s.startsWith("https://")) {
                            detectedClipboardUrl = s;
                            tvClipboardText.setText("Detected: " + s);
                            cardClipboardBanner.setVisibility(View.VISIBLE);
                        }
                    }
                }
            }
        } catch (Exception ignored) {}
    }

    private void inspectUrl(String url) {
        layoutLoading.setVisibility(View.VISIBLE);
        cardMediaInfo.setVisibility(View.GONE);
        btnInspect.setEnabled(false);

        executor.submit(() -> {
            try {
                MediaInfo info = extractionEngine.extract(url);
                mainHandler.post(() -> onExtractionSuccess(info));
            } catch (Exception e) {
                mainHandler.post(() -> onExtractionError(e.getMessage()));
            }
        });
    }

    private void onExtractionSuccess(MediaInfo info) {
        layoutLoading.setVisibility(View.GONE);
        btnInspect.setEnabled(true);
        currentMediaInfo = info;

        cardMediaInfo.setVisibility(View.VISIBLE);
        tvMediaTitle.setText(info.getTitle());
        tvMediaAuthor.setText(info.getAuthor());
        tvPlatformBadge.setText(info.getPlatform());

        if (info.getDurationSeconds() > 0) {
            tvDuration.setVisibility(View.VISIBLE);
            tvDuration.setText(FormatUtils.formatDuration(info.getDurationSeconds()));
        } else {
            tvDuration.setVisibility(View.GONE);
        }

        if (info.getThumbnailUrl() != null && !info.getThumbnailUrl().isEmpty()) {
            Glide.with(this)
                    .load(info.getThumbnailUrl())
                    .placeholder(R.drawable.ic_video)
                    .centerCrop()
                    .into(ivThumbnail);
        } else {
            ivThumbnail.setImageResource(R.drawable.ic_video);
        }
    }

    private void onExtractionError(String error) {
        layoutLoading.setVisibility(View.GONE);
        btnInspect.setEnabled(true);
        Toast.makeText(requireContext(), "Extraction error: " + (error != null ? error : "Unknown"), Toast.LENGTH_LONG).show();
    }

    private void startDownload() {
        if (currentMediaInfo == null) {
            Toast.makeText(requireContext(), "No media selected", Toast.LENGTH_SHORT).show();
            return;
        }

        boolean isAudio = toggleType.getCheckedButtonId() == R.id.btn_toggle_audio;
        String downloadUrl = null;
        String extension = isAudio ? "mp3" : "mp4";
        String qualityLabel = isAudio ? "MP3 320k" : "1080p HD";

        if (isAudio) {
            if (!currentMediaInfo.getAudioFormats().isEmpty()) {
                MediaFormat f = currentMediaInfo.getAudioFormats().get(0);
                downloadUrl = f.getDownloadUrl();
                extension = f.getExtension();
                qualityLabel = f.getLabel();
            } else if (!currentMediaInfo.getVideoFormats().isEmpty()) {
                MediaFormat f = currentMediaInfo.getVideoFormats().get(0);
                downloadUrl = f.getDownloadUrl();
                extension = "mp3";
            }
        } else {
            if (!currentMediaInfo.getVideoFormats().isEmpty()) {
                MediaFormat f = currentMediaInfo.getVideoFormats().get(0);
                downloadUrl = f.getDownloadUrl();
                extension = f.getExtension();
                qualityLabel = f.getLabel();
            }
        }

        if (downloadUrl == null) {
            Toast.makeText(requireContext(), "No stream URL found", Toast.LENGTH_SHORT).show();
            return;
        }

        DownloadItem item = new DownloadItem(
                "dl_" + System.currentTimeMillis(),
                currentMediaInfo.getTitle(),
                currentMediaInfo.getUrl(),
                downloadUrl,
                extension,
                isAudio
        );
        item.setThumbnailUrl(currentMediaInfo.getThumbnailUrl());
        item.setQualityLabel(qualityLabel);

        DownloadManager.getInstance(requireContext()).startDownload(item);

        Toast.makeText(requireContext(), "Download started: " + item.getTitle(), Toast.LENGTH_SHORT).show();

        if (getActivity() instanceof MainActivity) {
            ((MainActivity) getActivity()).navigateToDownloads();
        }
    }
}
