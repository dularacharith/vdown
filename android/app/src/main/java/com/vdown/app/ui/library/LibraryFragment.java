package com.vdown.app.ui.library;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;
import com.vdown.app.R;
import com.vdown.app.ui.adapters.LibraryAdapter;
import com.vdown.app.utils.FileUtils;
import java.io.File;
import java.util.List;

public class LibraryFragment extends Fragment {

    private SwipeRefreshLayout swipeRefresh;
    private RecyclerView recyclerLibrary;
    private View layoutEmpty;
    private LibraryAdapter adapter;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_library, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        swipeRefresh = view.findViewById(R.id.swipe_refresh);
        recyclerLibrary = view.findViewById(R.id.recycler_library);
        layoutEmpty = view.findViewById(R.id.layout_empty_library);

        adapter = new LibraryAdapter(this::refreshData);
        recyclerLibrary.setLayoutManager(new LinearLayoutManager(requireContext()));
        recyclerLibrary.setAdapter(adapter);

        swipeRefresh.setOnRefreshListener(this::refreshData);
        refreshData();
    }

    @Override
    public void onResume() {
        super.onResume();
        refreshData();
    }

    private void refreshData() {
        List<File> files = FileUtils.getLibraryFiles();
        adapter.updateList(files);
        swipeRefresh.setRefreshing(false);

        if (files.isEmpty()) {
            layoutEmpty.setVisibility(View.VISIBLE);
            recyclerLibrary.setVisibility(View.GONE);
        } else {
            layoutEmpty.setVisibility(View.GONE);
            recyclerLibrary.setVisibility(View.VISIBLE);
        }
    }
}
