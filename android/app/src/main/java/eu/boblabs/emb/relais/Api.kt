package eu.boblabs.emb.relais

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Client for the EMB relay API.
 *  - POST /api/relay/register  once, with the one-time pairing code (sends the public key)
 *  - GET  /api/relay/ping      signed
 *  - POST /api/relay/messages  signed
 */
class Api(private val settings: Settings) {

    sealed class Result {
        data class Ok(val body: JSONObject) : Result()
        data class Unauthorized(val code: String, val message: String) : Result()
        data class Failed(val message: String) : Result()
    }

    private val server get() = settings.server.trimEnd('/')

    fun register(code: String, publicKey: String, hardware: String): Result {
        val body = JSONObject().put("public_key", publicKey).put("key_hardware", hardware)
        return http("POST", "/api/relay/register", body.toString().toByteArray(Charsets.UTF_8),
            mapOf("Authorization" to "Bearer $code"))
    }

    fun ping(): Result = signed("GET", "/api/relay/ping", ByteArray(0))

    fun send(messages: List<CapturedMessage>): Result {
        val arr = JSONArray()
        for (m in messages) {
            arr.put(JSONObject().put("chat", m.chat).put("sender", m.sender).put("text", m.text).put("posted_at", m.postedAt))
        }
        return signed("POST", "/api/relay/messages", JSONObject().put("messages", arr).toString().toByteArray(Charsets.UTF_8))
    }

    private fun signed(method: String, path: String, body: ByteArray, retried: Boolean = false): Result {
        val ts = (System.currentTimeMillis() + settings.clockOffsetMs).toString()
        val nonce = RequestSigner.newNonce()
        val signature = try {
            DeviceKey.sign(RequestSigner.canonical(method, path, ts, nonce, body))
        } catch (e: Exception) {
            return Result.Unauthorized("no_key", "Clé de l'appareil absente : réassociez l'application")
        }
        val r = http(method, path, body, mapOf(
            "X-Relay-Device" to settings.deviceId.toString(),
            "X-Relay-Timestamp" to ts,
            "X-Relay-Nonce" to nonce,
            "X-Relay-Signature" to signature,
        ))
        // Phone clock too far off: learn the offset from the server and retry once.
        if (!retried && r is Result.Unauthorized && r.code == "clock" && lastServerTime > 0) {
            settings.clockOffsetMs = lastServerTime - System.currentTimeMillis()
            return signed(method, path, body, retried = true)
        }
        return r
    }

    private var lastServerTime = 0L

    private fun http(method: String, path: String, body: ByteArray, headers: Map<String, String>): Result {
        val conn = try {
            URL(server + path).openConnection() as HttpURLConnection
        } catch (e: Exception) {
            return Result.Failed("Adresse du serveur invalide")
        }
        return try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 20_000
            conn.setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            conn.setRequestProperty("Accept", "application/json")
            headers.forEach { (k, v) -> conn.setRequestProperty(k, v) }
            if (method == "POST") {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.setFixedLengthStreamingMode(body.size)          // sends Content-Length
                conn.outputStream.use { it.write(body) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(text) }.getOrNull() ?: JSONObject()
            lastServerTime = json.optLong("server_time", 0L)
            when {
                code in 200..299 -> Result.Ok(json)
                code == 401 -> Result.Unauthorized(json.optString("code"), json.optString("error", "refusé"))
                code == 404 -> Result.Failed("Module WhatsApp non activé sur le serveur (404)")
                code == 429 -> Result.Failed("Serveur : trop de requêtes, nouvel essai plus tard")
                else -> Result.Failed("Erreur serveur $code ${json.optString("error")}".trim())
            }
        } catch (e: IOException) {
            Result.Failed("Réseau : ${e.javaClass.simpleName} ${e.message.orEmpty()}".trim())
        } finally {
            conn.disconnect()
        }
    }
}
