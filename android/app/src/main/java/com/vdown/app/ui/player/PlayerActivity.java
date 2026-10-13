package com.vdown.app.ui.player;

import android.media.MediaPlayer;
import android.media.audiofx.LoudnessEnhancer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.MediaController;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.VideoView;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import com.google.android.material.button.MaterialButton;
import com.vdown.app.R;
import java.io.File;

public class PlayerActivity extends AppCompatActivity {
    public static final String EXTRA_FILE_PATH = "extra_file_path";
    public static final String EXTRA_MEDIA_TITLE = "extra_media_title";
    public static final String EXTRA_IS_AUDIO = "extra_is_audio";

    private VideoView videoView;
    private TextView tvPlayerTitle, tvAudioTitle;
    private LinearLayout layoutAudioView;
    private ImageButton btnBack;
    private MaterialButton btnAudioBoost;

    private LoudnessEnhancer loudnessEnhancer;
    private boolean isBoostEnabled = true;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_player);

        videoView = findViewById(R.id.video_view);
        tvPlayerTitle = findViewById(R.id.tv_player_title);
        tvAudioTitle = findViewById(R.id.tv_audio_title);
        layoutAudioView = findViewById(R.id.layout_audio_view);
        btnBack = findViewById(R.id.btn_back);
        btnAudioBoost = findViewById(R.id.btn_audio_boost);

        btnBack.setOnClickListener(v -> finish());

        String filePath = getIntent().getStringExtra(EXTRA_FILE_PATH);
        String mediaTitle = getIntent().getStringExtra(EXTRA_MEDIA_TITLE);
        boolean isAudio = getIntent().getBooleanExtra(EXTRA_IS_AUDIO, false);

        if (filePath == null) {
            Toast.makeText(this, "Media path is missing", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }

        File file = new File(filePath);
        if (!file.exists()) {
            Toast.makeText(this, "File does not exist: " + filePath, Toast.LENGTH_SHORT).show();
            finish();
            return;
        }

        tvPlayerTitle.setText(mediaTitle != null ? mediaTitle : file.getName());

        if (isAudio) {
            layoutAudioView.setVisibility(View.VISIBLE);
            tvAudioTitle.setText(mediaTitle != null ? mediaTitle : file.getName());
            videoView.setVisibility(View.GONE);
        } else {
            layoutAudioView.setVisibility(View.GONE);
            videoView.setVisibility(View.VISIBLE);
        }

        MediaController mediaController = new MediaController(this);
        mediaController.setAnchorView(videoView);
        videoView.setMediaController(mediaController);
        videoView.setVideoURI(Uri.fromFile(file));

        videoView.setOnPreparedListener(mp -> {
            applyAudioBoost(mp.getAudioSessionId());
            videoView.start();
        });

        btnAudioBoost.setOnClickListener(v -> toggleAudioBoost());

        videoView.setOnErrorListener((mp, what, extra) -> {
            Toast.makeText(this, "Error playing media file", Toast.LENGTH_SHORT).show();
            return true;
        });
    }

    private void applyAudioBoost(int audioSessionId) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            try {
                if (loudnessEnhancer != null) {
                    loudnessEnhancer.release();
                }
                loudnessEnhancer = new LoudnessEnhancer(audioSessionId);
                // Boost by +700 mB (+7 dB) to match official TikTok / platform loudness
                loudnessEnhancer.setTargetGain(700);
                loudnessEnhancer.setEnabled(isBoostEnabled);
            } catch (Exception ignored) {}
        }
    }

    private void toggleAudioBoost() {
        isBoostEnabled = !isBoostEnabled;
        if (loudnessEnhancer != null) {
            try {
                loudnessEnhancer.setEnabled(isBoostEnabled);
            } catch (Exception ignored) {}
        }
        if (isBoostEnabled) {
            btnAudioBoost.setText("Boost: ON (+7dB)");
            btnAudioBoost.setBackgroundColor(0xCC10B981);
            Toast.makeText(this, "Audio Gain Boost ON (+7dB)", Toast.LENGTH_SHORT).show();
        } else {
            btnAudioBoost.setText("Boost: OFF");
            btnAudioBoost.setBackgroundColor(0x6664748B);
            Toast.makeText(this, "Audio Gain Boost OFF", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (videoView.isPlaying()) {
            videoView.pause();
        }
    }

    @Override
    protected void onDestroy() {
        if (loudnessEnhancer != null) {
            try {
                loudnessEnhancer.release();
            } catch (Exception ignored) {}
        }
        super.onDestroy();
    }
}
