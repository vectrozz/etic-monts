package eu.boblabs.emb.relais

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/** Sends pending messages to the server; retried with backoff when offline or on errors. */
class UploadWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        val settings = Settings(applicationContext)
        if (!settings.isPaired) return Result.success()
        val store = Store.get(applicationContext)
        val api = Api(settings.server, settings.token)
        while (true) {
            val batch = store.pending(100)
            if (batch.isEmpty()) break
            when (val r = api.send(batch)) {
                is Api.Result.Ok -> {
                    store.markSent(batch.map { it.key })
                    settings.lastSyncAt = System.currentTimeMillis()
                    settings.lastError = null
                }
                is Api.Result.Unauthorized -> {
                    settings.lastError = "Jeton refusé par le serveur : réassociez l'application."
                    return Result.failure()
                }
                is Api.Result.Failed -> {
                    settings.lastError = r.message
                    return Result.retry()
                }
            }
        }
        return Result.success()
    }

    companion object {
        private val ONLINE = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(ONLINE)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork("upload", ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }

        /** Safety net: flush anything left behind every 15 minutes. */
        fun schedulePeriodic(context: Context) {
            val request = PeriodicWorkRequestBuilder<UploadWorker>(15, TimeUnit.MINUTES)
                .setConstraints(ONLINE)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork("upload-periodic", ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
