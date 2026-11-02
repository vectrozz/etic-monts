package eu.boblabs.emb.relais

import android.Manifest
import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.service.notification.NotificationListenerService
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.Person
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : Activity() {

    private lateinit var settings: Settings
    private lateinit var status: TextView
    private lateinit var recent: TextView
    private lateinit var server: EditText
    private lateinit var token: EditText
    private lateinit var groups: EditText
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private val time = SimpleDateFormat("EEE dd/MM HH:mm", Locale.FRANCE)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        settings = Settings(this)
        status = findViewById(R.id.status)
        recent = findViewById(R.id.recent)
        server = findViewById(R.id.server)
        token = findViewById(R.id.token)
        groups = findViewById(R.id.groups)
        findViewById<TextView>(R.id.version).text = getString(R.string.version, BuildConfig.VERSION_NAME)

        findViewById<Button>(R.id.btn_access).setOnClickListener {
            startActivity(Intent(android.provider.Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        findViewById<Button>(R.id.btn_battery).setOnClickListener { requestIgnoreBattery() }
        findViewById<Button>(R.id.btn_test).setOnClickListener { testConnection() }
        findViewById<Button>(R.id.btn_send).setOnClickListener {
            UploadWorker.enqueue(this)
            toast(getString(R.string.sending))
            main.postDelayed({ refresh() }, 2500)
        }
        findViewById<Button>(R.id.btn_save).setOnClickListener { save() }
        findViewById<Button>(R.id.btn_simulate).apply {
            visibility = if (BuildConfig.DEBUG) View.VISIBLE else View.GONE
            setOnClickListener { simulate("Ferme Test", "batavia rouge 2 colis, poireaux 5 colis, carottes 4 colis") }
        }

        fillForm()
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        if (hasNotificationAccess()) {
            // Some phones unbind listeners after an update or a kill: ask for a rebind.
            NotificationListenerService.requestRebind(ComponentName(this, WhatsAppListener::class.java))
        }
        refresh()
    }

    // ------------------------------------------------------------------ pairing / config

    private fun handleIntent(intent: Intent?) {
        val data: Uri? = intent?.data
        if (data != null && data.scheme == "embrelais" && data.host == "pair") {
            val s = data.getQueryParameter("server").orEmpty()
            val t = data.getQueryParameter("token").orEmpty()
            if (!s.startsWith("http") || t.isEmpty()) {
                toast(getString(R.string.pair_invalid))
                return
            }
            settings.server = s
            settings.token = t
            data.getQueryParameter("groups")?.takeIf { it.isNotBlank() }?.let { settings.groupsText = it }
            data.getQueryParameter("name")?.let { settings.deviceName = it }
            settings.lastError = null
            fillForm()
            toast(getString(R.string.paired, s))
            testConnection()
        }
        if (BuildConfig.DEBUG) {
            intent?.getStringExtra("simulate")?.let { text ->
                simulate(intent.getStringExtra("simulate_sender") ?: "Ferme Test", text,
                         intent.getStringExtra("simulate_group"))
            }
        }
    }

    private fun fillForm() {
        server.setText(settings.server)
        token.setText(settings.token)
        groups.setText(settings.groupsText)
    }

    private fun save() {
        settings.server = server.text.toString()
        settings.token = token.text.toString()
        settings.groupsText = groups.text.toString()
        fillForm()
        toast(getString(R.string.saved))
        refresh()
    }

    private fun testConnection() {
        if (!settings.isPaired) {
            toast(getString(R.string.not_paired))
            return
        }
        val api = Api(settings.server, settings.token)
        io.execute {
            val msg = when (val r = api.ping()) {
                is Api.Result.Ok -> getString(R.string.test_ok, r.body.optString("device"))
                is Api.Result.Unauthorized -> getString(R.string.test_unauthorized)
                is Api.Result.Failed -> r.message
            }
            main.post { toast(msg); refresh() }
        }
    }

    // ------------------------------------------------------------------ status

    private fun hasNotificationAccess() =
        NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)

    private fun ignoresBatteryOptimizations() =
        getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)

    private fun requestIgnoreBattery() {
        if (ignoresBatteryOptimizations()) {
            toast(getString(R.string.battery_ok))
            return
        }
        startActivity(
            Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName"))
        )
    }

    private fun refresh() {
        val store = Store.get(this)
        io.execute {
            val (pending, sent) = store.counts()
            val rows = store.recent(15)
            main.post { render(pending, sent, rows) }
        }
    }

    private fun render(pending: Int, sent: Int, rows: List<Store.Row>) {
        val ok = "✓"
        val ko = "✗"
        val g = settings.groups
        val lines = mutableListOf(
            if (hasNotificationAccess()) "$ok ${getString(R.string.st_access_ok)}" else "$ko ${getString(R.string.st_access_ko)}",
            if (ignoresBatteryOptimizations()) "$ok ${getString(R.string.st_battery_ok)}" else "! ${getString(R.string.st_battery_ko)}",
            if (settings.isPaired) "$ok ${getString(R.string.st_server, settings.server)}" else "$ko ${getString(R.string.st_not_paired)}",
            if (g.isNotEmpty()) "$ok ${getString(R.string.st_groups, g.joinToString(" · "))}" else "$ko ${getString(R.string.st_no_group)}",
            getString(R.string.st_counts, pending, sent),
        )
        if (settings.lastSyncAt > 0) lines += getString(R.string.st_last_sync, time.format(Date(settings.lastSyncAt)))
        settings.lastSeenChat?.let { chat ->
            val followed = GroupFilter(g).matches(chat)
            lines += getString(if (followed) R.string.st_last_chat_followed else R.string.st_last_chat_ignored, chat)
        }
        settings.lastError?.let { lines += "! $it" }
        status.text = lines.joinToString("\n")
        // Setup buttons disappear once their step is done.
        findViewById<Button>(R.id.btn_access).visibility = if (hasNotificationAccess()) View.GONE else View.VISIBLE
        findViewById<Button>(R.id.btn_battery).visibility = if (ignoresBatteryOptimizations()) View.GONE else View.VISIBLE

        recent.text = if (rows.isEmpty()) getString(R.string.no_messages) else rows.joinToString("\n\n") { r ->
            val state = if (r.sentAt != null) ok else "…"
            "$state ${time.format(Date(r.message.postedAt))} · ${r.message.sender}\n${r.message.text.take(160)}"
        }
    }

    // ------------------------------------------------------------------ debug: fake WhatsApp message

    private fun simulate(sender: String, text: String, groupName: String? = null) {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
            return
        }
        val group = groupName ?: settings.groups.firstOrNull() ?: "Groupe test"
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("simulation", "Simulation", NotificationManager.IMPORTANCE_DEFAULT))
        val style = NotificationCompat.MessagingStyle(Person.Builder().setName("Moi").build())
            .setConversationTitle(group)
            .setGroupConversation(true)
            .addMessage(text, System.currentTimeMillis(), Person.Builder().setName(sender).build())
        val n = NotificationCompat.Builder(this, "simulation")
            .setSmallIcon(R.drawable.ic_stat_relais)
            .setStyle(style)
            .build()
        NotificationManagerCompat.from(this).notify((System.currentTimeMillis() % 100000).toInt(), n)
        toast("Message simulé dans « $group »")
        main.postDelayed({ refresh() }, 2500)
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
