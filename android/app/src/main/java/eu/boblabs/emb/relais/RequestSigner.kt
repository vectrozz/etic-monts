package eu.boblabs.emb.relais

import java.security.MessageDigest
import java.security.SecureRandom

/**
 * What the phone signs for each request — must match the server
 * (eticmonts/relay_auth.py::canonical):
 *
 *     METHOD \n PATH \n TIMESTAMP \n NONCE \n sha256_hex(BODY)
 */
object RequestSigner {
    private val random = SecureRandom()

    fun canonical(method: String, path: String, timestamp: String, nonce: String, body: ByteArray): ByteArray =
        "${method.uppercase()}\n$path\n$timestamp\n$nonce\n${sha256Hex(body)}".toByteArray(Charsets.UTF_8)

    fun newNonce(): String {
        val bytes = ByteArray(16)
        random.nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    fun sha256Hex(data: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }
}
