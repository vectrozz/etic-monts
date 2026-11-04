package eu.boblabs.emb.relais

import android.content.Context

/** App configuration, stored in the app's private storage. */
class Settings(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("relais", Context.MODE_PRIVATE)

    var server: String
        get() = prefs.getString("server", "").orEmpty()
        set(v) = prefs.edit().putString("server", v.trim().trimEnd('/')).apply()

    /** Server-side id of this phone, set by a successful pairing (0 = not paired). */
    var deviceId: Int
        get() = prefs.getInt("device_id", 0)
        set(v) = prefs.edit().putInt("device_id", v).apply()

    /** strongbox | tee | software — where the device key lives. */
    var keyHardware: String
        get() = prefs.getString("key_hardware", "").orEmpty()
        set(v) = prefs.edit().putString("key_hardware", v).apply()

    /** Correction applied to the phone clock (learnt from the server when it is off). */
    var clockOffsetMs: Long
        get() = prefs.getLong("clock_offset_ms", 0L)
        set(v) = prefs.edit().putLong("clock_offset_ms", v).apply()

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

    /**
     * Names (never the content) of the group conversations seen recently, most
     * recent first, so the user can pick the groups to follow with one tap —
     * e.g. the groups of a WhatsApp community, which each have their own name.
     */
    val recentChats: List<String>
        get() = prefs.getString("recent_chats", "").orEmpty().split('\n').filter { it.isNotBlank() }

    @Synchronized
    fun rememberChat(chat: String) {
        val list = (listOf(chat) + recentChats.filter { it != chat }).take(20)
        prefs.edit().putString("recent_chats", list.joinToString("\n")).apply()
    }

    fun isFollowed(chat: String) = GroupFilter(groups).matches(chat)

    fun follow(chat: String) {
        if (!isFollowed(chat)) groupsText = (groups + chat).joinToString("\n")
    }

    fun unfollow(chat: String) {
        val key = GroupFilter.normalize(chat)
        groupsText = groups.filter { GroupFilter.normalize(it) != key }.joinToString("\n")
    }

    val isPaired: Boolean get() = server.startsWith("http") && deviceId > 0
}
