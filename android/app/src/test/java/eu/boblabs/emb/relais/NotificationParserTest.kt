package eu.boblabs.emb.relais

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationParserTest {

    private fun notif(
        title: String? = null,
        conversationTitle: String? = null,
        messages: List<RawMessage> = emptyList(),
        text: String? = null,
        bigText: String? = null,
        summary: Boolean = false,
    ) = RawNotification(
        packageName = "com.whatsapp", title = title, conversationTitle = conversationTitle,
        isGroupConversation = conversationTitle != null, text = text, bigText = bigText,
        messages = messages, postTime = 1_000L, isGroupSummary = summary,
    )

    @Test fun messagingStyleGroup() {
        val n = notif(
            conversationTitle = "Producteurs EMB (3 messages)",
            messages = listOf(
                RawMessage("Lucie Coteau", "batavia rouge 2 colis, poireaux 5 colis", 1730550000000),
                RawMessage(null, "message envoyé par moi", 1730550001000),
                RawMessage("‪+33 6 12 34 56 78‬", "carottes 4 colis", 1730550002000),
            ),
        )
        val out = NotificationParser.parse(n)
        assertEquals(2, out.size)
        assertEquals(CapturedMessage("Producteurs EMB", "Lucie Coteau", "batavia rouge 2 colis, poireaux 5 colis", 1730550000000), out[0])
        assertEquals("+33 6 12 34 56 78", out[1].sender)
    }

    @Test fun frenchCountSuffixAndBidiMarks() {
        assertEquals("Producteurs EMB", NotificationParser.chatTitle("⁨Producteurs EMB⁩ (2 nouveaux messages)"))
    }

    @Test fun legacyTitleLayouts() {
        val a = NotificationParser.parse(notif(title = "Lucie @ Producteurs EMB", text = "salade x6"))
        assertEquals(listOf(CapturedMessage("Producteurs EMB", "Lucie", "salade x6", 1_000L)), a)
        val b = NotificationParser.parse(notif(title = "Producteurs EMB: Lucie", text = "short", bigText = "poireaux 5 colis\ncarottes 4 colis"))
        assertEquals("poireaux 5 colis\ncarottes 4 colis", b.single().text)
        assertEquals("Producteurs EMB", b.single().chat)
    }

    @Test fun summariesDeletedAndSystemTextsAreIgnored() {
        assertTrue(NotificationParser.parse(notif(title = "WhatsApp", text = "12 messages from 3 chats", summary = true)).isEmpty())
        assertTrue(NotificationParser.parse(notif(conversationTitle = "G", messages = listOf(RawMessage("A", "Ce message a été supprimé", 5)))).isEmpty())
        assertTrue(NotificationParser.parse(notif(title = "WhatsApp", text = "Checking for new messages")).isEmpty())
    }

    @Test fun keyMatchesServerFormula() {
        // python: hashlib.sha256("Producteurs EMB\x1fLucie Coteau\x1f1730550000000\x1fpoireaux 5 colis — 2,5 kg".encode()).hexdigest()
        val m = CapturedMessage("Producteurs EMB", "Lucie Coteau", "poireaux 5 colis — 2,5 kg", 1730550000000)
        assertEquals("288e23ea9a727d6c63955a0de06b40ec7c6f43edaf80cd413b3e10037d8d3b0f", m.key)
        assertFalse(m.key == m.copy(postedAt = 1730550000001).key)
    }

    @Test fun groupFilter() {
        val f = GroupFilter(GroupFilter.parse("  Producteurs EMB \n\nAutre, groupe\n"))
        assertTrue(f.matches("producteurs  emb"))
        assertTrue(f.matches("⁨Autre, groupe⁩"))
        assertFalse(f.matches("Famille"))
        assertTrue(GroupFilter(emptyList()).isEmpty)
    }
}
