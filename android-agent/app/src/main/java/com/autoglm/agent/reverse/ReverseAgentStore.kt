package com.autoglm.agent.reverse

import android.content.Context

data class ReverseAgentSession(
    val serverBaseUrl: String,
    val agentId: String,
    val agentToken: String,
    val pairingId: String,
    val websocketPath: String,
    val heartbeatIntervalSeconds: Int,
)

class ReverseAgentStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun loadSession(): ReverseAgentSession? {
        val serverBaseUrl = prefs.getString(KEY_SERVER_BASE_URL, null)?.trim().orEmpty()
        val agentId = prefs.getString(KEY_AGENT_ID, null)?.trim().orEmpty()
        val agentToken = prefs.getString(KEY_AGENT_TOKEN, null)?.trim().orEmpty()
        val pairingId = prefs.getString(KEY_PAIRING_ID, null)?.trim().orEmpty()
        val websocketPath = prefs.getString(KEY_WEBSOCKET_PATH, null)?.trim().orEmpty()
        val heartbeatIntervalSeconds = prefs.getInt(KEY_HEARTBEAT_INTERVAL_SECONDS, 10)

        if (
            serverBaseUrl.isBlank() ||
            agentId.isBlank() ||
            agentToken.isBlank() ||
            pairingId.isBlank() ||
            websocketPath.isBlank()
        ) {
            return null
        }

        return ReverseAgentSession(
            serverBaseUrl = serverBaseUrl,
            agentId = agentId,
            agentToken = agentToken,
            pairingId = pairingId,
            websocketPath = websocketPath,
            heartbeatIntervalSeconds = heartbeatIntervalSeconds.coerceAtLeast(5),
        )
    }

    fun saveSession(session: ReverseAgentSession) {
        prefs.edit()
            .putString(KEY_SERVER_BASE_URL, session.serverBaseUrl)
            .putString(KEY_AGENT_ID, session.agentId)
            .putString(KEY_AGENT_TOKEN, session.agentToken)
            .putString(KEY_PAIRING_ID, session.pairingId)
            .putString(KEY_WEBSOCKET_PATH, session.websocketPath)
            .putInt(KEY_HEARTBEAT_INTERVAL_SECONDS, session.heartbeatIntervalSeconds.coerceAtLeast(5))
            .apply()
    }

    fun clearSession() {
        prefs.edit()
            .remove(KEY_SERVER_BASE_URL)
            .remove(KEY_AGENT_ID)
            .remove(KEY_AGENT_TOKEN)
            .remove(KEY_PAIRING_ID)
            .remove(KEY_WEBSOCKET_PATH)
            .remove(KEY_HEARTBEAT_INTERVAL_SECONDS)
            .apply()
    }

    companion object {
        private const val PREFS_NAME = "reverse_agent_store"
        private const val KEY_SERVER_BASE_URL = "server_base_url"
        private const val KEY_AGENT_ID = "agent_id"
        private const val KEY_AGENT_TOKEN = "agent_token"
        private const val KEY_PAIRING_ID = "pairing_id"
        private const val KEY_WEBSOCKET_PATH = "websocket_path"
        private const val KEY_HEARTBEAT_INTERVAL_SECONDS = "heartbeat_interval_seconds"
    }
}
