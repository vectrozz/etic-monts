package eu.boblabs.emb.relais

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Minimal client for the EMB server relay API: GET /api/relay/ping, POST /api/relay/messages. */
class Api(private val server: String, private val token: String) {

    sealed class Result {
        data class Ok(val body: JSONObject) : Result()
        data class Unauthorized(val message: String) : Result()
        data class Failed(val message: String) : Result()
    }

    fun ping(): Result = call("GET", "/api/relay/ping", null)

    fun send(messages: List<CapturedMessage>): Result {
        val arr = JSONArray()
        for (m in messages) {
            arr.put(JSONObject().put("chat", m.chat).put("sender", m.sender).put("text", m.text).put("posted_at", m.postedAt))
        }
        return call("POST", "/api/relay/messages", JSONObject().put("messages", arr))
    }

    private fun call(method: String, path: String, body: JSONObject?): Result {
        val conn = try {
            URL(server.trimEnd('/') + path).openConnection() as HttpURLConnection
        } catch (e: Exception) {
            return Result.Failed("Adresse du serveur invalide")
        }
        return try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 20_000
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            conn.setRequestProperty("Accept", "application/json")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(text) }.getOrNull() ?: JSONObject()
            when {
                code in 200..299 -> Result.Ok(json)
                code == 401 -> Result.Unauthorized(json.optString("error", "jeton refusé"))
                code == 404 -> Result.Failed("Module WhatsApp non activé sur le serveur (404)")
                else -> Result.Failed("Erreur serveur $code ${json.optString("error")}".trim())
            }
        } catch (e: IOException) {
            Result.Failed("Réseau : ${e.javaClass.simpleName} ${e.message.orEmpty()}".trim())
        } finally {
            conn.disconnect()
        }
    }
}
