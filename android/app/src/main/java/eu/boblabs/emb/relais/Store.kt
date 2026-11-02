package eu.boblabs.emb.relais

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * Local queue of captured messages. A message stays "pending" until the server
 * acknowledged it, so nothing is lost while the phone is offline.
 */
class Store private constructor(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "relais.db", null, 1) {

    data class Row(val message: CapturedMessage, val capturedAt: Long, val sentAt: Long?)

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE messages (
                key TEXT PRIMARY KEY, chat TEXT NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL,
                posted_at INTEGER NOT NULL, captured_at INTEGER NOT NULL, sent_at INTEGER)"""
        )
        db.execSQL("CREATE INDEX idx_pending ON messages (sent_at, posted_at)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    /** Returns how many were new (already-seen messages are ignored). */
    fun insert(messages: List<CapturedMessage>): Int {
        var added = 0
        writableDatabase.run {
            beginTransaction()
            try {
                for (m in messages) {
                    val v = ContentValues().apply {
                        put("key", m.key); put("chat", m.chat); put("sender", m.sender)
                        put("text", m.text); put("posted_at", m.postedAt)
                        put("captured_at", System.currentTimeMillis())
                    }
                    if (insertWithOnConflict("messages", null, v, SQLiteDatabase.CONFLICT_IGNORE) != -1L) added++
                }
                setTransactionSuccessful()
            } finally {
                endTransaction()
            }
        }
        return added
    }

    fun pending(limit: Int): List<CapturedMessage> =
        query("sent_at IS NULL", "posted_at ASC", limit).map { it.message }

    fun recent(limit: Int): List<Row> = query(null, "posted_at DESC", limit)

    fun markSent(keys: List<String>) {
        val now = System.currentTimeMillis()
        writableDatabase.run {
            beginTransaction()
            try {
                for (k in keys) execSQL("UPDATE messages SET sent_at = ? WHERE key = ?", arrayOf(now, k))
                // keep the history small: last 1000 sent messages
                execSQL(
                    "DELETE FROM messages WHERE sent_at IS NOT NULL AND key NOT IN " +
                        "(SELECT key FROM messages WHERE sent_at IS NOT NULL ORDER BY posted_at DESC LIMIT 1000)"
                )
                setTransactionSuccessful()
            } finally {
                endTransaction()
            }
        }
    }

    fun counts(): Pair<Int, Int> {
        readableDatabase.rawQuery(
            "SELECT SUM(sent_at IS NULL), SUM(sent_at IS NOT NULL) FROM messages", null
        ).use { c ->
            c.moveToFirst()
            return c.getInt(0) to c.getInt(1)
        }
    }

    private fun query(where: String?, order: String, limit: Int): List<Row> {
        val out = mutableListOf<Row>()
        readableDatabase.query(
            "messages", arrayOf("chat", "sender", "text", "posted_at", "captured_at", "sent_at"),
            where, null, null, null, order, limit.toString()
        ).use { c ->
            while (c.moveToNext()) {
                out += Row(
                    CapturedMessage(c.getString(0), c.getString(1), c.getString(2), c.getLong(3)),
                    c.getLong(4), if (c.isNull(5)) null else c.getLong(5),
                )
            }
        }
        return out
    }

    companion object {
        @Volatile private var instance: Store? = null
        fun get(context: Context): Store =
            instance ?: synchronized(this) { instance ?: Store(context).also { instance = it } }
    }
}
