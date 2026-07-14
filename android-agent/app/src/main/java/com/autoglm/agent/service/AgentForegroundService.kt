package com.autoglm.agent.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.autoglm.agent.MainActivity
import com.autoglm.agent.R
import com.autoglm.agent.http.AgentHttpServer
import com.autoglm.agent.reverse.ReverseAgentClient

class AgentForegroundService : Service() {
    private var server: AgentHttpServer? = null
    private lateinit var reverseAgentClient: ReverseAgentClient

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "onCreate")
        createNotificationChannel()
        reverseAgentClient = ReverseAgentClient.getInstance(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "onStartCommand action=${intent?.action} startId=$startId serverRunning=${server != null}")
        when (intent?.action) {
            ACTION_STOP -> stopAgent()
            ACTION_ENABLE_CAPTURE -> enableCaptureMode()
            ACTION_START, null -> startAgent()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        Log.w(TAG, "onDestroy running=$running projectionModeEnabled=$projectionModeEnabled")
        server?.stop()
        server = null
        reverseAgentClient.stop()
        running = false
        projectionModeEnabled = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startAgent() {
        if (server == null) {
            server = AgentHttpServer(this, DEFAULT_PORT).also {
                it.start(SOCKET_READ_TIMEOUT, false)
            }
            Log.i(TAG, "HTTP server started on port=$DEFAULT_PORT")
        }
        startForegroundWithType(captureEnabled = false)
        reverseAgentClient.start()
        running = true
        Log.i(TAG, "startAgent complete captureEnabled=false")
    }

    private fun enableCaptureMode() {
        if (server == null) {
            server = AgentHttpServer(this, DEFAULT_PORT).also {
                it.start(SOCKET_READ_TIMEOUT, false)
            }
            Log.i(TAG, "HTTP server started during capture enable on port=$DEFAULT_PORT")
        }
        startForegroundWithType(captureEnabled = true)
        reverseAgentClient.start()
        projectionModeEnabled = true
        running = true
        Log.i(TAG, "enableCaptureMode complete projectionModeEnabled=true")
    }

    private fun stopAgent() {
        Log.i(TAG, "stopAgent")
        stopForeground(STOP_FOREGROUND_REMOVE)
        projectionModeEnabled = false
        stopSelf()
    }

    private fun startForegroundWithType(captureEnabled: Boolean) {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val type = if (captureEnabled) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC or
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            } else {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            }
            startForeground(NOTIFICATION_ID, notification, type)
            Log.i(TAG, "startForeground type=$type captureEnabled=$captureEnabled")
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_content, DEFAULT_PORT))
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .setContentIntent(openIntent)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        )
        manager.createNotificationChannel(channel)
    }

    companion object {
        private const val TAG = "AutoGLM/FGS"
        private const val ACTION_START = "com.autoglm.agent.action.START"
        private const val ACTION_STOP = "com.autoglm.agent.action.STOP"
        private const val ACTION_ENABLE_CAPTURE = "com.autoglm.agent.action.ENABLE_CAPTURE"
        private const val CHANNEL_ID = "autoglm_agent_runtime"
        private const val NOTIFICATION_ID = 1001
        private const val DEFAULT_PORT = 18080
        private const val SOCKET_READ_TIMEOUT = 5_000

        @Volatile
        private var running: Boolean = false
        @Volatile
        private var projectionModeEnabled: Boolean = false

        fun createStartIntent(context: Context): Intent =
            Intent(context, AgentForegroundService::class.java).setAction(ACTION_START)

        fun createStopIntent(context: Context): Intent =
            Intent(context, AgentForegroundService::class.java).setAction(ACTION_STOP)

        fun createEnableCaptureIntent(context: Context): Intent =
            Intent(context, AgentForegroundService::class.java).setAction(ACTION_ENABLE_CAPTURE)

        fun isRunning(): Boolean = running

        fun currentPort(): Int = DEFAULT_PORT

        fun isProjectionModeEnabled(): Boolean = projectionModeEnabled
    }
}
