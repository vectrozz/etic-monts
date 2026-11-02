package eu.boblabs.emb.relais

import android.content.Context

/** App configuration, stored in the app's private storage. */
class Settings(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("relais", Context.MODE_PRIVATE)

    var server: String
        get() = prefs.getString("server", "").orEmpty()
        set(v) = prefs.edit().putString("server", v.trim().trimEnd('/')).apply()

    var token: String
        get() = prefs.getString("token", "").orEmpty()
        set(v) = prefs.edit().putString("token", v.trim()).apply()

    /** One WhatsApp group name per line. */
    var groupsText: String
        get() = prefs.getString("groups", "").orEmpty()
        set(v) = prefs.edit().putString("groups", GroupFilter.parse(v).joinToString("\n")).apply()

    val groups: List<String> get() = GroupFilter.parse(groupsText)

    var deviceName: String
        get() = prefs.getString("device_name", "").orEmpty()
        set(v) = prefs.edit().putString("device_name", v).apply()

    var lastSyncAt: Long
        get() = prefs.getLong("last_sync_at", 0L)
        set(v) = prefs.edit().putLong("last_sync_at", v).apply()

    var lastError: String?
        get() = prefs.getString("last_error", null)
        set(v) = prefs.edit().putString("last_error", v).apply()

    /** Name (never the content) of the last WhatsApp conversation seen, to help set the exact group name. */
    var lastSeenChat: String?
        get() = prefs.getString("last_seen_chat", null)
        set(v) = prefs.edit().putString("last_seen_chat", v).apply()

    val isPaired: Boolean get() = server.startsWith("http") && token.isNotEmpty()
}
