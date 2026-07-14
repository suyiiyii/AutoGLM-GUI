package com.autoglm.agent.reverse

import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

data class ReverseAgentUiState(
    val connectionStatus: String = "unpaired",
    val statusMessage: String = "Reverse agent not paired yet.",
    val serverBaseUrl: String? = null,
    val agentId: String? = null,
    val pairingId: String? = null,
)

class ReverseAgentClient private constructor(context: Context) {
    private val appContext = context.applicationContext
    private val store = ReverseAgentStore(appContext)
    private val commandExecutor = CommandExecutor(appContext)
    private val httpClient = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
    private val scheduler: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val listeners = CopyOnWriteArraySet<(ReverseAgentUiState) -> Unit>()
    private val reconnectAttempt = AtomicInteger(0)

    @Volatile
    private var session: ReverseAgentSession? = store.loadSession()

    @Volatile
    private var webSocket: WebSocket? = null

    @Volatile
    private var reconnectEnabled: Boolean = false

    @Volatile
    private var heartbeatTask: ScheduledFuture<*>? = null

    @Volatile
    private var reconnectTask: ScheduledFuture<*>? = null

    @Volatile
    private var lastHeartbeatAckAtMillis: Long = 0L

    @Volatile
    private var uiState: ReverseAgentUiState = session?.toPairedState()
        ?: ReverseAgentUiState()

    fun currentState(): ReverseAgentUiState = uiState

    fun addListener(listener: (ReverseAgentUiState) -> Unit) {
        listeners.add(listener)
        listener(uiState)
    }

    fun removeListener(listener: (ReverseAgentUiState) -> Unit) {
        listeners.remove(listener)
    }

    fun start() {
        reconnectEnabled = true
        connectIfConfigured()
    }

    fun stop() {
        reconnectEnabled = false
        cancelReconnect()
        cancelHeartbeat()
        webSocket?.cancel()
        webSocket = null
        session?.let {
            updateState(
                it.toState(
                    connectionStatus = "paired",
                    statusMessage = "Reverse agent paused. Start the agent to reconnect.",
                )
            )
        } ?: updateState(ReverseAgentUiState())
    }

    fun shutdown() {
        stop()
        httpClient.dispatcher.executorService.shutdown()
        httpClient.connectionPool.evictAll()
        scheduler.shutdownNow()
    }

    fun pair(
        serverBaseUrl: String,
        pairingCode: String,
        callback: (Result<ReverseAgentSession>) -> Unit,
    ) {
        val normalizedBaseUrl = normalizeServerBaseUrl(serverBaseUrl)
        val normalizedPairingCode = pairingCode.trim().uppercase()
        if (normalizedBaseUrl == null) {
            callbackOnMain(callback, Result.failure(IllegalArgumentException("server_base_url_invalid")))
            return
        }
        if (normalizedPairingCode.length < 6) {
            callbackOnMain(callback, Result.failure(IllegalArgumentException("pairing_code_invalid")))
            return
        }

        reconnectEnabled = true
        updateState(
            ReverseAgentUiState(
                connectionStatus = "pairing",
                statusMessage = "Claiming reverse-agent pairing…",
                serverBaseUrl = normalizedBaseUrl,
            )
        )

        scheduler.execute {
            try {
                val requestBody = JSONObject()
                    .put("pairing_code", normalizedPairingCode)
                    .put("display_name", Build.MODEL ?: "Android Agent")
                    .put("app_version", appVersion())
                    .put("platform", "android")
                    .put("capabilities", JSONArray(CAPABILITIES))
                    .put(
                        "metadata",
                        JSONObject()
                            .put("model", Build.MODEL ?: "Android")
                            .put("manufacturer", Build.MANUFACTURER ?: "Android")
                            .put("sdk_int", Build.VERSION.SDK_INT),
                    )
                    .toString()
                    .toRequestBody(JSON_MEDIA_TYPE)

                val request = Request.Builder()
                    .url("$normalizedBaseUrl/api/reverse_agents/pairings/claim")
                    .post(requestBody)
                    .build()

                httpClient.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        throw IOException(parseErrorBody(response) ?: "pairing_claim_failed_${response.code}")
                    }
                    val body = response.body?.string().orEmpty()
                    val payload = JSONObject(body)
                    val pairedSession = ReverseAgentSession(
                        serverBaseUrl = normalizedBaseUrl,
                        agentId = payload.getString("agent_id"),
                        agentToken = payload.getString("agent_token"),
                        pairingId = payload.getString("pairing_id"),
                        websocketPath = payload.getString("websocket_path"),
                        heartbeatIntervalSeconds = payload.optInt("heartbeat_interval_seconds", 10).coerceAtLeast(5),
                    )
                    session = pairedSession
                    store.saveSession(pairedSession)
                    updateState(
                        pairedSession.toState(
                            connectionStatus = "paired",
                            statusMessage = "Pairing claimed. Opening reverse-agent session…",
                        )
                    )
                    connect(pairedSession, resetBackoff = true)
                    callbackOnMain(callback, Result.success(pairedSession))
                }
            } catch (error: Exception) {
                Log.e(TAG, "pair failed", error)
                updateState(
                    ReverseAgentUiState(
                        connectionStatus = "error",
                        statusMessage = error.message ?: error.javaClass.simpleName,
                        serverBaseUrl = normalizedBaseUrl,
                    )
                )
                callbackOnMain(callback, Result.failure(error))
            }
        }
    }

    fun clearPairing() {
        reconnectEnabled = false
        cancelReconnect()
        cancelHeartbeat()
        webSocket?.cancel()
        webSocket = null
        session = null
        store.clearSession()
        updateState(
            ReverseAgentUiState(
                connectionStatus = "unpaired",
                statusMessage = "Reverse-agent pairing cleared.",
            )
        )
    }

    private fun connectIfConfigured() {
        val configured = session ?: run {
            updateState(ReverseAgentUiState())
            return
        }
        connect(configured, resetBackoff = false)
    }

    private fun connect(configured: ReverseAgentSession, resetBackoff: Boolean) {
        if (!reconnectEnabled) {
            return
        }
        if (resetBackoff) {
            reconnectAttempt.set(0)
        }
        cancelReconnect()
        cancelHeartbeat()
        webSocket?.cancel()
        webSocket = null

        val webSocketUrl = configured.websocketUrl()
        updateState(
            configured.toState(
                connectionStatus = "connecting",
                statusMessage = "Connecting reverse-agent websocket…",
            )
        )

        val request = Request.Builder()
            .url("$webSocketUrl?token=${configured.agentToken}")
            .build()
        webSocket = httpClient.newWebSocket(request, ReverseWebSocketListener(configured))
    }

    private fun scheduleHeartbeat(configured: ReverseAgentSession, intervalSeconds: Int) {
        cancelHeartbeat()
        lastHeartbeatAckAtMillis = System.currentTimeMillis()
        heartbeatTask = scheduler.scheduleAtFixedRate(
            {
                val socket = webSocket ?: return@scheduleAtFixedRate
                val now = System.currentTimeMillis()
                if (lastHeartbeatAckAtMillis > 0L && now - lastHeartbeatAckAtMillis > intervalSeconds * 2_000L) {
                    updateState(
                        configured.toState(
                            connectionStatus = "stale",
                            statusMessage = "Reverse-agent heartbeat is stale. Waiting for reconnect…",
                        )
                    )
                }
                val heartbeat = JSONObject()
                    .put("type", "heartbeat")
                    .put("display_name", Build.MODEL ?: "Android Agent")
                    .put("app_version", appVersion())
                    .put("capabilities", JSONArray(CAPABILITIES))
                    .put(
                        "metadata",
                        JSONObject()
                            .put("model", Build.MODEL ?: "Android")
                            .put("manufacturer", Build.MANUFACTURER ?: "Android")
                            .put("sdk_int", Build.VERSION.SDK_INT),
                    )
                val heartbeatText = heartbeat.toString()
                socket.send(heartbeatText)
            },
            0L,
            intervalSeconds.toLong(),
            TimeUnit.SECONDS,
        )
    }

    private fun scheduleReconnect(configured: ReverseAgentSession, reason: String) {
        if (!reconnectEnabled) {
            return
        }
        cancelReconnect()
        val attempt = reconnectAttempt.incrementAndGet()
        val delaySeconds = minOf(30, 2 shl (attempt - 1))
        updateState(
            configured.toState(
                connectionStatus = "paired",
                statusMessage = "Reverse-agent disconnected ($reason). Reconnecting in ${delaySeconds}s…",
            )
        )
        reconnectTask = scheduler.schedule(
            { connect(configured, resetBackoff = false) },
            delaySeconds.toLong(),
            TimeUnit.SECONDS,
        )
    }

    private fun cancelHeartbeat() {
        heartbeatTask?.cancel(false)
        heartbeatTask = null
    }

    private fun cancelReconnect() {
        reconnectTask?.cancel(false)
        reconnectTask = null
    }

    private fun updateState(newState: ReverseAgentUiState) {
        uiState = newState
        mainHandler.post {
            listeners.forEach { listener -> listener(newState) }
        }
    }

    private fun callbackOnMain(
        callback: (Result<ReverseAgentSession>) -> Unit,
        result: Result<ReverseAgentSession>,
    ) {
        mainHandler.post { callback(result) }
    }

    private fun parseErrorBody(response: Response): String? {
        val body = response.body?.string()?.trim().orEmpty()
        if (body.isBlank()) {
            return null
        }
        return try {
            JSONObject(body).optString("detail").ifBlank {
                JSONObject(body).optString("message").ifBlank { body }
            }
        } catch (_: Exception) {
            body
        }
    }

    private fun normalizeServerBaseUrl(raw: String): String? {
        val trimmed = raw.trim().trimEnd('/')
        if (trimmed.isBlank()) {
            return null
        }
        return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
            trimmed
        } else {
            "http://$trimmed"
        }
    }

    private fun appVersion(): String {
        return try {
            val packageInfo = appContext.packageManager.getPackageInfo(appContext.packageName, 0)
            packageInfo.versionName ?: "0.0.0"
        } catch (_: Exception) {
            "0.0.0"
        }
    }

    private fun ReverseAgentSession.toState(
        connectionStatus: String,
        statusMessage: String,
    ): ReverseAgentUiState = ReverseAgentUiState(
        connectionStatus = connectionStatus,
        statusMessage = statusMessage,
        serverBaseUrl = serverBaseUrl,
        agentId = agentId,
        pairingId = pairingId,
    )

    private fun ReverseAgentSession.toPairedState(): ReverseAgentUiState =
        toState(
            connectionStatus = "paired",
            statusMessage = "Reverse agent paired. Start the agent to reconnect.",
        )

    private fun ReverseAgentSession.websocketUrl(): String {
        val schemeAdjusted = when {
            serverBaseUrl.startsWith("https://") -> "wss://${serverBaseUrl.removePrefix("https://")}"
            serverBaseUrl.startsWith("http://") -> "ws://${serverBaseUrl.removePrefix("http://")}"
            else -> "ws://$serverBaseUrl"
        }
        return "$schemeAdjusted$websocketPath"
    }

    private inner class ReverseWebSocketListener(
        private val configured: ReverseAgentSession,
    ) : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            Log.i(TAG, "websocket open agentId=${configured.agentId}")
            reconnectAttempt.set(0)
            updateState(
                configured.toState(
                    connectionStatus = "connecting",
                    statusMessage = "Reverse-agent websocket opened. Waiting for session_ready…",
                )
            )
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val message = JSONObject(text)
            when (message.optString("type")) {
                "session_ready" -> {
                    val heartbeatIntervalSeconds =
                        message.optInt("heartbeat_interval_seconds", configured.heartbeatIntervalSeconds)
                            .coerceAtLeast(5)
                    val updatedSession = configured.copy(
                        heartbeatIntervalSeconds = heartbeatIntervalSeconds,
                    )
                    session = updatedSession
                    store.saveSession(updatedSession)
                    updateState(
                        updatedSession.toState(
                            connectionStatus = "connected",
                            statusMessage = "Reverse-agent session ready.",
                        )
                    )
                    scheduleHeartbeat(updatedSession, heartbeatIntervalSeconds)
                }

                "heartbeat_ack" -> {
                    lastHeartbeatAckAtMillis = System.currentTimeMillis()
                    updateState(
                        configured.toState(
                            connectionStatus = message.optString("connection_status", "connected"),
                            statusMessage = "Reverse-agent heartbeat acknowledged.",
                        )
                    )
                }

                "pong" -> Unit

                "command" -> {
                    val commandId = message.optString("command_id", "")
                    val commandType = message.optString("command_type", "")
                    val payload = message.optJSONObject("payload") ?: JSONObject()
                    val activeSocket = webSocket
                    scheduler.execute {
                        try {
                            val result = commandExecutor.execute(commandId, commandType, payload)
                            activeSocket.send(result.toString())
                        } catch (error: Exception) {
                            Log.e(TAG, "failed to execute command $commandType", error)
                        }
                    }
                }

                "error" -> {
                    updateState(
                        configured.toState(
                            connectionStatus = "error",
                            statusMessage = message.optString("message", "reverse_agent_error"),
                        )
                    )
                }
            }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            Log.w(TAG, "unexpected binary websocket payload size=${bytes.size}")
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            Log.w(TAG, "websocket closing code=$code reason=$reason")
            webSocket.close(code, reason)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            Log.w(TAG, "websocket closed code=$code reason=$reason")
            cancelHeartbeat()
            this@ReverseAgentClient.webSocket = null
            scheduleReconnect(configured, reason.ifBlank { "closed" })
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.e(TAG, "websocket failure code=${response?.code}", t)
            cancelHeartbeat()
            this@ReverseAgentClient.webSocket = null
            scheduleReconnect(configured, t.message ?: t.javaClass.simpleName)
        }
    }

    companion object {
        private const val TAG = "AutoGLM/ReverseClient"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val CAPABILITIES = listOf("screenshot", "tap", "swipe", "type_text", "current_app")

        @Volatile
        private var instance: ReverseAgentClient? = null

        fun getInstance(context: Context): ReverseAgentClient =
            instance ?: synchronized(this) {
                instance ?: ReverseAgentClient(context).also { instance = it }
            }
    }
}
