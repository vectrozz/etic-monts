package eu.boblabs.emb.relais

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * Receives the notifications of the phone (permission granted by the user in
 * Android settings). Keeps WhatsApp messages of the configured groups only;
 * everything else is ignored and never stored.
 */
class WhatsAppListener : NotificationListenerService() {

    override fun onListenerConnected() {
        UploadWorker.schedulePeriodic(this)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        // Debug builds also accept their own simulated notifications (emulator tests).
        val sources = if (BuildConfig.DEBUG) NotificationParser.WHATSAPP_PACKAGES + packageName
        else NotificationParser.WHATSAPP_PACKAGES
        if (sbn.packageName !in sources) return

        val settings = Settings(this)
        try {
            val parsed = NotificationParser.parse(toRaw(sbn))
            // Only the conversation name is remembered, to help type the exact group name.
            parsed.firstOrNull()?.let { settings.lastSeenChat = it.chat }
            val filter = GroupFilter(settings.groups)
            if (!settings.isPaired || filter.isEmpty) return
            val captured = parsed.filter { filter.matches(it.chat) }
            if (captured.isEmpty()) return
            if (Store.get(this).insert(captured) > 0) UploadWorker.enqueue(this)
        } catch (e: Exception) {
            // Never crash the listener on an unexpected notification layout.
            Log.w(TAG, "could not read notification", e)
        }
    }

    private fun toRaw(sbn: StatusBarNotification): RawNotification {
        val n = sbn.notification
        val extras = n.extras
        val style = NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(n)
        val messages = style?.messages.orEmpty().map {
            RawMessage(it.person?.name?.toString(), it.text?.toString(), it.timestamp)
        }
        return RawNotification(
            packageName = sbn.packageName,
            title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString(),
            conversationTitle = style?.conversationTitle?.toString()
                ?: extras.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString(),
            isGroupConversation = style?.isGroupConversation ?: false,
            text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString(),
            bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString(),
            messages = messages,
            postTime = sbn.postTime,
            isGroupSummary = (n.flags and Notification.FLAG_GROUP_SUMMARY) != 0,
        )
    }

    companion object {
        private const val TAG = "EmbRelais"
    }
}
