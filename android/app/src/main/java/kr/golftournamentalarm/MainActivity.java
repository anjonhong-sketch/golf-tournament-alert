package kr.golftournamentalarm;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputFilter;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.google.firebase.FirebaseApp;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.firestore.CollectionReference;
import com.google.firebase.firestore.DocumentSnapshot;
import com.google.firebase.firestore.FieldValue;
import com.google.firebase.firestore.FirebaseFirestore;
import com.google.firebase.firestore.ListenerRegistration;
import com.google.firebase.firestore.Query;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

public final class MainActivity extends Activity {
    private static final String FEED = "https://raw.githubusercontent.com/anjonhong-sketch/"
            + "golf-tournament-alert/main/data/tournaments.json";
    private static final int GREEN = Color.rgb(24, 76, 60);
    private static final String UNKNOWN = "미확인";
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private JSONObject feed;
    private LinearLayout page;
    private ListenerRegistration listener;
    private int screen;
    private boolean roomOpen;
    private boolean archive;
    private boolean candidates;
    private boolean refreshing;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(GREEN);
        getWindow().setNavigationBarColor(GREEN);
        try {
            feed = parseFeed(getPreferences(0).getString("feed", ""));
        } catch (Exception ignored) {
            // An empty or outdated cache can be replaced by the next refresh.
        }
        showList(feed == null ? "대회 정보를 불러오는 중…" : "저장된 대회 정보");
        refresh();
    }

    private static JSONObject parseFeed(String content) throws Exception {
        JSONObject parsed = new JSONObject(content);
        parsed.getJSONArray("tournaments");
        return parsed;
    }

    private void refresh() {
        if (refreshing) return;
        refreshing = true;
        network.execute(() -> {
            try {
                HttpsURLConnection connection = (HttpsURLConnection) new URL(FEED).openConnection();
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(10000);
                connection.setUseCaches(false);
                String json;
                try {
                    if (connection.getResponseCode() != 200) throw new IOException("Feed unavailable");
                    try (var input = connection.getInputStream()) {
                        byte[] bytes = readFeed(input);
                        json = new String(bytes, StandardCharsets.UTF_8);
                    }
                } finally {
                    connection.disconnect();
                }
                JSONObject latest = parseFeed(json);
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    refreshing = false;
                    feed = latest;
                    getPreferences(0).edit().putString("feed", json).apply();
                    if (!roomOpen) showList(null);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    refreshing = false;
                    if (!roomOpen) showList(feed == null
                            ? "대회 정보를 불러오지 못했습니다. 새로고침을 눌러 다시 시도하세요."
                            : "새로고침 실패 · 저장된 대회 정보");
                });
            }
        });
    }

    private static byte[] readFeed(java.io.InputStream input) throws IOException {
        var output = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (output.size() + count > 2_000_000) throw new IOException("Feed too large");
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private void showList(String message) {
        roomOpen = false;
        newPage("골프대회 알리미");
        button(page, "새로고침", () -> {
            showList("대회 정보를 불러오는 중…");
            refresh();
        });
        button(page, archive ? "진행·예정 대회 보기" : "종료된 대회 보기", () -> {
            archive = !archive;
            candidates = false;
            showList(message);
        });
        button(page, candidates ? "대회 목록 보기" : "검토 중인 후보 보기", () -> {
            candidates = !candidates;
            showList(message);
        });
        if (candidates) label(page, "참가 가능 여부와 세부 정보 확인이 필요한 검색 결과입니다.", 14, false);
        if (message != null) label(page, message, 15, false);
        LinearLayout cards = scroll(page);
        JSONArray list = feed == null ? null : feed.optJSONArray(candidates ? "candidates" : "tournaments");
        if (list == null) list = new JSONArray();
        int count = 0;
        for (int index = 0; index < list.length(); index++) {
            JSONObject event = list.optJSONObject(index);
            if (event == null || (!candidates && "종료".equals(value(event, "event_status")) != archive)) continue;
            count++;
            label(cards, value(event, "title"), 21, true);
            label(cards, value(event, "category") + " · " + value(event, "event_status"), 15, false);
            String start = value(event, "start_date");
            String end = value(event, "end_date");
            label(cards, "일정  " + (start.equals(end) ? start : start + " ~ " + end)
                    + "\n지역  " + value(event, "region")
                    + "\n참가비  " + value(event, "entry_fee")
                    + "\n접수  " + value(event, "registration_status")
                    + "\n참가 조건  " + value(event, "eligibility"), 16, false);
            String original = value(event, "official_url");
            String url = UNKNOWN.equals(original) ? value(event, "discovery_url") : original;
            if ("https".equals(Uri.parse(url).getScheme())) {
                button(cards, candidates ? "후보 출처" : "대회 원문", () -> {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (ActivityNotFoundException error) {
                        toast("원문을 열 수 있는 브라우저가 없습니다.");
                    }
                });
            }
            String id = value(event, "id");
            if (!candidates && id.matches("[a-z0-9-]{1,80}")) {
                LinearLayout actions = new LinearLayout(this);
                actions.setOrientation(LinearLayout.HORIZONTAL);
                cards.addView(actions);
                button(actions, "대회 채팅", () -> showRoom(event, "chat"));
                button(actions, "참가 후기", () -> showRoom(event, "reviews"));
            }
        }
        if (count == 0 && feed != null) label(cards, "표시할 대회가 없습니다.", 16, false);
    }

    private void showRoom(JSONObject event, String kind) {
        roomOpen = true;
        boolean chat = kind.equals("chat");
        int limit = chat ? 300 : 1500;
        newPage(chat ? "대회 채팅" : "참가 후기");
        button(page, "대회 목록", () -> showList(null));
        label(page, value(event, "title"), 18, true);
        if (FirebaseApp.getApps(this).isEmpty()) {
            label(page, "커뮤니티 서버 연결 설정이 필요합니다.", 16, false);
            return;
        }
        label(page, chat ? "이 채팅은 다른 앱 사용자에게 공개됩니다."
                : "참가 후기를 공유해 주세요. 다른 앱 사용자에게 공개됩니다.", 14, false);
        LinearLayout posts = scroll(page);
        EditText input = new EditText(this);
        input.setHint(chat ? "메시지 입력" : "참가 후기 입력");
        input.setMaxLines(4);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(limit)});
        page.addView(input);
        Button submit = button(page, chat ? "보내기" : "후기 등록", () -> {});
        submit.setEnabled(false);
        label(posts, "연결 중…", 16, false);
        int active = screen;
        FirebaseAuth auth = FirebaseAuth.getInstance();
        if (auth.getCurrentUser() == null) {
            auth.signInAnonymously().addOnCompleteListener(this, task -> {
                if (active != screen) return;
                if (task.isSuccessful()) openRoom(event, kind, active, posts, input, submit);
                else {
                    posts.removeAllViews();
                    label(posts, "연결에 실패했습니다.", 16, false);
                    button(posts, "다시 시도", () -> showRoom(event, kind));
                }
            });
        } else {
            openRoom(event, kind, active, posts, input, submit);
        }
    }

    private void openRoom(JSONObject event, String kind, int active, LinearLayout posts,
                          EditText input, Button submit) {
        String uid = FirebaseAuth.getInstance().getUid();
        if (uid == null) return;
        CollectionReference room = FirebaseFirestore.getInstance().collection("tournaments")
                .document(value(event, "id")).collection(kind);
        listener = room.orderBy("createdAt", Query.Direction.DESCENDING).limit(100)
                .addSnapshotListener((snapshot, error) -> {
                    if (active != screen) return;
                    posts.removeAllViews();
                    if (error != null || snapshot == null) {
                        submit.setEnabled(false);
                        label(posts, "글을 불러오지 못했습니다.", 16, false);
                        button(posts, "다시 시도", () -> showRoom(event, kind));
                        return;
                    }
                    if (snapshot.isEmpty()) label(posts, "아직 글이 없습니다.", 16, false);
                    for (DocumentSnapshot post : snapshot) {
                        String author = post.getString("author");
                        boolean mine = uid.equals(author);
                        Date created = post.getDate("createdAt", DocumentSnapshot.ServerTimestampBehavior.ESTIMATE);
                        String name = mine ? "나" : "참가자 " + (author == null
                                ? "" : author.substring(0, Math.min(5, author.length())));
                        label(posts, name + (created == null ? "" : " · "
                                + DateFormat.getDateTimeInstance().format(created)), 14, true);
                        label(posts, post.getString("body"), 17, false);
                        if (mine && !post.getMetadata().hasPendingWrites()) {
                            button(posts, "내 글 삭제", () -> new android.app.AlertDialog.Builder(this)
                                    .setMessage("이 글을 삭제할까요?")
                                    .setNegativeButton("취소", null)
                                    .setPositiveButton("삭제", (dialog, which) -> post.getReference().delete()
                                            .addOnFailureListener(this, failure -> toast("삭제하지 못했습니다.")))
                                    .show());
                        }
                    }
                });
        submit.setEnabled(true);
        submit.setOnClickListener(view -> {
            String body = input.getText().toString().trim();
            if (body.isEmpty()) return;
            submit.setEnabled(false);
            input.setEnabled(false);
            Map<String, Object> post = new HashMap<>();
            post.put("author", uid);
            post.put("body", body);
            post.put("createdAt", FieldValue.serverTimestamp());
            room.add(post)
                    .addOnCompleteListener(this, task -> {
                        if (active != screen) return;
                        input.setEnabled(true);
                        submit.setEnabled(true);
                        if (task.isSuccessful()) input.setText("");
                        else toast("글을 등록하지 못했습니다.");
                    });
        });
    }

    private static String value(JSONObject object, String key) {
        if (object.isNull(key)) return UNKNOWN;
        String text = object.optString(key, UNKNOWN).trim();
        return text.isEmpty() ? UNKNOWN : text;
    }

    private void newPage(String title) {
        closeListener();
        page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(16), dp(8), dp(16), dp(12));
        page.setBackgroundColor(Color.rgb(246, 250, 247));
        if (android.os.Build.VERSION.SDK_INT >= 35) {
            page.setOnApplyWindowInsetsListener((view, insets) -> {
                var bars = insets.getInsets(android.view.WindowInsets.Type.systemBars()
                        | android.view.WindowInsets.Type.displayCutout()
                        | android.view.WindowInsets.Type.ime());
                view.setPadding(dp(16) + bars.left, dp(8) + bars.top,
                        dp(16) + bars.right, dp(12) + bars.bottom);
                return insets;
            });
        }
        setContentView(page);
        label(page, title, 26, true).setTextColor(GREEN);
    }

    private LinearLayout scroll(LinearLayout parent) {
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(content);
        parent.addView(scroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        return content;
    }

    private TextView label(LinearLayout parent, String text, int size, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(Color.rgb(27, 39, 34));
        view.setPadding(0, dp(7), 0, dp(4));
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        parent.addView(view);
        return view;
    }

    private Button button(LinearLayout parent, String text, Runnable action) {
        Button view = new Button(this);
        view.setAllCaps(false);
        view.setText(text);
        view.setOnClickListener(clicked -> action.run());
        parent.addView(view);
        return view;
    }

    private int dp(int amount) {
        return Math.round(amount * getResources().getDisplayMetrics().density);
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }

    private void closeListener() {
        screen++;
        if (listener != null) {
            listener.remove();
            listener = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (roomOpen) showList(null);
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        closeListener();
        network.shutdownNow();
        super.onDestroy();
    }
}
