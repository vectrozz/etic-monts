package eu.boblabs.emb.relais

import java.security.MessageDigest
import java.text.Normalizer

/** One message as found inside a notification (no Android types: unit-testable). */
data class RawMessage(val sender: String?, val text: String?, val timestamp: Long)

/** The parts of a WhatsApp notification we look at. */
data class RawNotification(
    val packageName: String,
    val title: String?,
    val conversationTitle: String?,
    val isGroupConversation: Boolean,
    val text: String?,
    val bigText: String?,
    val messages: List<RawMessage>,
    val postTime: Long,
    val isGroupSummary: Boolean,
)

/** A group message ready to be sent to the server. */
data class CapturedMessage(val chat: String, val sender: String, val text: String, val postedAt: Long) {
    /** Same formula as the server (eticmonts/relay.py::dedup_key). */
    val key: String
        get() = sha256("$chat\u001f$sender\u001f$postedAt\u001f$text")
}

private fun sha256(s: String): String =
    MessageDigest.getInstance("SHA-256").digest(s.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

private val BIDI = Regex("[‎‏‪-‮⁦-⁩]")
private val SPACES = Regex("\\s+")

internal fun cleanName(s: String): String = s.replace(BIDI, "").replace(SPACES, " ").trim()

object NotificationParser {
    val WHATSAPP_PACKAGES = setOf("com.whatsapp", "com.whatsapp.w4b")

    // "Producteurs (3 messages)", "Producteurs (2 nouveaux messages)"
    private val COUNT_SUFFIX = Regex("""\s*\(\d+\s+[^)]*\)\s*$""")
    private val SENDER_AT_GROUP = Regex("""^(.+?) @ (.+)$""")
    private val GROUP_COLON_SENDER = Regex("""^(.+?): (.+)$""")
    private val IGNORED = listOf(
        Regex("""^(ce message a été supprimé|this message was deleted|vous avez supprimé ce message)\.?$""", RegexOption.IGNORE_CASE),
        Regex("""^(checking for new messages|recherche de nouveaux messages).*""", RegexOption.IGNORE_CASE),
        Regex("""^\d+ (new )?messages?( from \d+ chats?)?$""", RegexOption.IGNORE_CASE),
        Regex("""^\d+ (nouveaux )?messages?( dans \d+ discussions?)?$""", RegexOption.IGNORE_CASE),
    )

    fun chatTitle(s: String): String = cleanName(s).replace(COUNT_SUFFIX, "").trim()

    private fun isIgnored(text: String) = IGNORED.any { it.matches(text) }

    /** "Sender @ Group" or "Group: Sender" → (group, sender). */
    fun splitTitle(title: String?): Pair<String, String>? {
        val t = cleanName(title ?: return null)
        SENDER_AT_GROUP.matchEntire(t)?.let { return chatTitle(it.groupValues[2]) to it.groupValues[1].trim() }
        GROUP_COLON_SENDER.matchEntire(t)?.let { return chatTitle(it.groupValues[1]) to it.groupValues[2].trim() }
        return null
    }

    fun parse(n: RawNotification): List<CapturedMessage> {
        if (n.isGroupSummary) return emptyList()

        if (n.messages.isNotEmpty()) {
            val chat = n.conversationTitle?.let(::chatTitle)?.takeIf { it.isNotEmpty() }
                ?: splitTitle(n.title)?.first
                ?: return emptyList()
            return n.messages.mapNotNull { m ->
                val sender = cleanName(m.sender.orEmpty())
                val text = m.text.orEmpty().trim()
                // sender == null: our own messages (MessagingStyle "user")
                if (sender.isEmpty() || text.isEmpty() || isIgnored(text)) null
                else CapturedMessage(chat, sender, text, if (m.timestamp > 0) m.timestamp else n.postTime)
            }
        }

        // Older notification layout: no MessagingStyle, sender in the title.
        val (chat, sender) = splitTitle(n.title) ?: return emptyList()
        val text = (n.bigText ?: n.text).orEmpty().trim()
        if (text.isEmpty() || isIgnored(text)) return emptyList()
        return listOf(CapturedMessage(chat, sender, text, n.postTime))
    }
}

/** Only the configured groups leave the phone. Empty filter = nothing is captured. */
class GroupFilter(groups: Collection<String>) {
    private val wanted = groups.map(::normalize).filter { it.isNotEmpty() }.toSet()

    val isEmpty: Boolean get() = wanted.isEmpty()

    fun matches(chat: String): Boolean = normalize(chat) in wanted

    companion object {
        fun normalize(s: String): String =
            Normalizer.normalize(cleanName(s), Normalizer.Form.NFKC).lowercase()

        /** One group per line (group names may contain commas). */
        fun parse(text: String): List<String> =
            text.split('\n').map { cleanName(it) }.filter { it.isNotEmpty() }.distinct()
    }
}
