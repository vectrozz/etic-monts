package eu.boblabs.emb.relais

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RequestSignerTest {

    /** Same vector as the server: python -c 'from eticmonts.relay_auth import canonical; …' */
    @Test fun canonicalMatchesServer() {
        val body = "{\"messages\":[{\"text\":\"poireaux 5 colis — été\"}]}".toByteArray(Charsets.UTF_8)
        val c = RequestSigner.canonical("post", "/api/relay/messages", "1730550000000",
            "00112233445566778899aabbccddeeff", body)
        assertEquals(
            "POST\n/api/relay/messages\n1730550000000\n00112233445566778899aabbccddeeff\n" +
                "502afccc97f66a693291b300fa5621ba5bdb9fb537c2ca7eebad9979db7d6b0b",
            String(c, Charsets.UTF_8),
        )
    }

    @Test fun noncesAre32HexAndUnique() {
        val a = RequestSigner.newNonce()
        val b = RequestSigner.newNonce()
        assertTrue(Regex("^[0-9a-f]{32}$").matches(a))
        assertNotEquals(a, b)
    }
}
