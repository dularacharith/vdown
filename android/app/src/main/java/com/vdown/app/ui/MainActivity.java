package com.vdown.app.ui;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.vdown.app.R;
import com.vdown.app.ui.downloads.DownloadsFragment;
import com.vdown.app.ui.home.HomeFragment;
import com.vdown.app.ui.library.LibraryFragment;
import com.vdown.app.ui.settings.SettingsFragment;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends AppCompatActivity {

    private BottomNavigationView bottomNav;
    private final HomeFragment homeFragment = new HomeFragment();
    private final DownloadsFragment downloadsFragment = new DownloadsFragment();
    private final LibraryFragment libraryFragment = new LibraryFragment();
    private final SettingsFragment settingsFragment = new SettingsFragment();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        bottomNav = findViewById(R.id.bottom_navigation);
        setupBottomNav();
        checkPermissions();

        if (savedInstanceState == null) {
            loadFragment(homeFragment);
        }

        handleIncomingIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIncomingIntent(intent);
    }

    private void setupBottomNav() {
        bottomNav.setOnItemSelectedListener(item -> {
            int itemId = item.getItemId();
            if (itemId == R.id.nav_home) {
                loadFragment(homeFragment);
                return true;
            } else if (itemId == R.id.nav_downloads) {
                loadFragment(downloadsFragment);
                return true;
            } else if (itemId == R.id.nav_library) {
                loadFragment(libraryFragment);
                return true;
            } else if (itemId == R.id.nav_settings) {
                loadFragment(settingsFragment);
                return true;
            }
            return false;
        });
    }

    private void loadFragment(Fragment fragment) {
        getSupportFragmentManager()
                .beginTransaction()
                .replace(R.id.fragment_container, fragment)
                .commit();
    }

    public void navigateToDownloads() {
        bottomNav.setSelectedItemId(R.id.nav_downloads);
    }

    private void handleIncomingIntent(Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();

        String extractedUrl = null;
        if (Intent.ACTION_SEND.equals(action)) {
            String sharedText = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (sharedText != null) {
                extractedUrl = extractUrl(sharedText);
            }
            if (extractedUrl == null && intent.getStringExtra(Intent.EXTRA_SUBJECT) != null) {
                extractedUrl = extractUrl(intent.getStringExtra(Intent.EXTRA_SUBJECT));
            }
            if (extractedUrl == null && intent.getClipData() != null && intent.getClipData().getItemCount() > 0) {
                CharSequence cs = intent.getClipData().getItemAt(0).getText();
                if (cs != null) {
                    extractedUrl = extractUrl(cs.toString());
                }
            }
        } else if (Intent.ACTION_VIEW.equals(action) && intent.getData() != null) {
            extractedUrl = extractUrl(intent.getDataString());
        }

        if (extractedUrl != null) {
            bottomNav.setSelectedItemId(R.id.nav_home);
            loadFragment(homeFragment);
            homeFragment.setUrlAndInspect(extractedUrl);
        }
    }

    private String extractUrl(String text) {
        Pattern pattern = Pattern.compile("https?://[\\w\\d:#@%/;$()~_?\\+-=\\\\\\.&]+", Pattern.CASE_INSENSITIVE);
        Matcher matcher = pattern.matcher(text);
        if (matcher.find()) {
            return matcher.group(0);
        }
        return text.trim().startsWith("http") ? text.trim() : null;
    }

    private void checkPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(
                        this,
                        new String[]{Manifest.permission.POST_NOTIFICATIONS},
                        101
                );
            }
        }
    }
}
