package com.autoglm.agent.reverse

import android.content.Context
import android.util.Log
import com.autoglm.agent.projection.ScreenCaptureController
import com.autoglm.agent.service.DeviceAccessibilityService
import org.json.JSONObject

class CommandExecutor(private val context: Context) {
    fun execute(commandId: String, commandType: String, payload: JSONObject): JSONObject {
        val startedAt = System.currentTimeMillis() / 1000.0
        return try {
            val resultPayload = when (commandType) {
                "screenshot" -> executeScreenshot()
                "tap" -> executeTap(payload)
                "swipe" -> executeSwipe(payload)
                "type_text" -> executeTypeText(payload)
                "current_app" -> executeCurrentApp()
                else -> throw IllegalArgumentException("unsupported_command_type: $commandType")
            }
            successResult(commandId, resultPayload, startedAt)
        } catch (error: Exception) {
            Log.e(TAG, "command failed: $commandType", error)
            failureResult(commandId, error.message ?: error.javaClass.simpleName, startedAt)
        }
    }

    private fun executeScreenshot(): JSONObject {
        val screenshot = ScreenCaptureController.capture(context, 10_000L)
        return JSONObject()
            .put("base64_data", screenshot.base64Data)
            .put("width", screenshot.width)
            .put("height", screenshot.height)
            .put("is_sensitive", false)
    }

    private fun executeTap(payload: JSONObject): JSONObject {
        val service = accessibilityService()
        val success = service.tap(payload.requiredInt("x"), payload.requiredInt("y"))
        return JSONObject().put("success", success)
    }

    private fun executeSwipe(payload: JSONObject): JSONObject {
        val service = accessibilityService()
        val success = service.swipe(
            startX = payload.requiredInt("start_x"),
            startY = payload.requiredInt("start_y"),
            endX = payload.requiredInt("end_x"),
            endY = payload.requiredInt("end_y"),
            durationMs = payload.optInt("duration_ms", 300).coerceAtLeast(50).toLong(),
        )
        return JSONObject().put("success", success)
    }

    private fun executeTypeText(payload: JSONObject): JSONObject {
        val service = accessibilityService()
        val success = service.typeText(payload.requiredString("text"))
        return JSONObject().put("success", success)
    }

    private fun executeCurrentApp(): JSONObject {
        val service = accessibilityService()
        return JSONObject().put("app_name", service.currentApp())
    }

    private fun accessibilityService(): DeviceAccessibilityService {
        return DeviceAccessibilityService.instance
            ?: throw IllegalStateException("accessibility_service_not_connected")
    }

    private fun successResult(
        commandId: String,
        payload: JSONObject,
        startedAt: Double,
    ): JSONObject {
        return JSONObject()
            .put("type", "command_result")
            .put("command_id", commandId)
            .put("success", true)
            .put("payload", payload)
            .put("error", JSONObject.NULL)
            .put("started_at", startedAt)
            .put("finished_at", System.currentTimeMillis() / 1000.0)
    }

    private fun failureResult(
        commandId: String,
        error: String,
        startedAt: Double,
    ): JSONObject {
        return JSONObject()
            .put("type", "command_result")
            .put("command_id", commandId)
            .put("success", false)
            .put("payload", JSONObject())
            .put("error", error)
            .put("started_at", startedAt)
            .put("finished_at", System.currentTimeMillis() / 1000.0)
    }

    companion object {
        private const val TAG = "AutoGLM/CommandExecutor"
    }
}

private fun JSONObject.requiredInt(key: String): Int {
    if (!has(key)) {
        throw IllegalArgumentException("missing required field: $key")
    }
    return getInt(key)
}

private fun JSONObject.requiredString(key: String): String {
    if (!has(key)) {
        throw IllegalArgumentException("missing required field: $key")
    }
    return getString(key)
}
