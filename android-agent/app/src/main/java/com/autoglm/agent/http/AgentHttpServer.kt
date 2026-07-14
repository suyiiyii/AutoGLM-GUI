package com.autoglm.agent.http

import android.content.Context
import android.os.Build
import android.util.Log
import com.autoglm.agent.projection.ScreenCaptureController
import com.autoglm.agent.service.DeviceAccessibilityService
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

class AgentHttpServer(
    private val context: Context,
    port: Int,
    private val deviceId: String = DEFAULT_DEVICE_ID,
) : NanoHTTPD("127.0.0.1", port) {
    override fun serve(session: IHTTPSession): Response {
        return try {
            route(session)
        } catch (error: MissingCapabilityException) {
            Log.w(TAG, "missing capability for ${session.method} ${session.uri}: ${error.code} ${error.message}")
            json(
                newFixedLengthResponse(
                    Response.Status.SERVICE_UNAVAILABLE,
                    JSON_MIME_TYPE,
                    JSONObject()
                        .put("error", error.code)
                        .put("message", error.message)
                        .toString(),
                ),
            )
        } catch (error: IllegalArgumentException) {
            Log.w(TAG, "invalid request for ${session.method} ${session.uri}: ${error.message}")
            json(
                newFixedLengthResponse(
                    Response.Status.BAD_REQUEST,
                    JSON_MIME_TYPE,
                    JSONObject()
                        .put("error", "invalid_request")
                        .put("message", error.message ?: "invalid request")
                        .toString(),
                ),
            )
        } catch (error: Exception) {
            Log.e(TAG, "internal error for ${session.method} ${session.uri}", error)
            json(
                newFixedLengthResponse(
                    Response.Status.INTERNAL_ERROR,
                    JSON_MIME_TYPE,
                    JSONObject()
                        .put("error", "internal_error")
                        .put("message", error.message ?: error.javaClass.simpleName)
                        .toString(),
                ),
            )
        }
    }

    private fun route(session: IHTTPSession): Response {
        val method = session.method
        val uri = session.uri.trimEnd('/')

        return when {
            method == Method.GET && uri == "/health" -> jsonResponse(
                JSONObject()
                    .put("status", "ok")
                    .put("service", "android-agent")
                    .put("version", "0.2.0")
                    .put("accessibility_enabled", DeviceAccessibilityService.isConnected())
                    .put("screen_capture_ready", ScreenCaptureController.hasPermission()),
            )

            method == Method.GET && uri == "/devices" -> {
                val devices = JSONArray().put(
                    JSONObject()
                        .put("device_id", deviceId)
                        .put("status", "online")
                        .put("model", Build.MODEL ?: "Android")
                        .put("platform", "android")
                        .put("connection_type", "remote"),
                )
                json(newFixedLengthResponse(Response.Status.OK, JSON_MIME_TYPE, devices.toString()))
            }

            method == Method.POST && uri == "/connect" -> jsonResponse(
                JSONObject()
                    .put("success", true)
                    .put("message", "Android Agent runs locally and is always connected."),
            )

            method == Method.POST && uri == "/disconnect" -> jsonResponse(
                JSONObject()
                    .put("success", true)
                    .put("message", "No-op for local Android Agent."),
            )

            method == Method.GET && uri == "/device/$deviceId/current_app" -> {
                val service = accessibilityService()
                jsonResponse(JSONObject().put("app_name", service.currentApp()))
            }

            method == Method.POST && uri == "/device/$deviceId/screenshot" -> {
                val body = readJsonBody(session)
                val timeout = body.optInt("timeout", 10).coerceAtLeast(1)
                val result = ScreenCaptureController.capture(context, timeout * 1000L)
                jsonResponse(
                    JSONObject()
                        .put("base64_data", result.base64Data)
                        .put("width", result.width)
                        .put("height", result.height)
                        .put("is_sensitive", false),
                )
            }

            method == Method.POST && uri == "/device/$deviceId/tap" -> {
                val body = readJsonBody(session)
                val service = accessibilityService()
                val success = service.tap(body.requiredInt("x"), body.requiredInt("y"))
                jsonResponse(JSONObject().put("success", success))
            }

            method == Method.POST && uri == "/device/$deviceId/swipe" -> {
                val body = readJsonBody(session)
                val service = accessibilityService()
                val success = service.swipe(
                    startX = body.requiredInt("start_x"),
                    startY = body.requiredInt("start_y"),
                    endX = body.requiredInt("end_x"),
                    endY = body.requiredInt("end_y"),
                    durationMs = body.optInt("duration_ms", 300).coerceAtLeast(50).toLong(),
                )
                jsonResponse(JSONObject().put("success", success))
            }

            method == Method.POST && uri == "/device/$deviceId/type_text" -> {
                val body = readJsonBody(session)
                val service = accessibilityService()
                val success = service.typeText(body.requiredString("text"))
                jsonResponse(JSONObject().put("success", success))
            }

            uri.startsWith("/device/$deviceId") -> json(
                newFixedLengthResponse(
                    Response.Status.NOT_IMPLEMENTED,
                    JSON_MIME_TYPE,
                    JSONObject()
                        .put("error", "not_implemented")
                        .put("path", session.uri)
                        .toString(),
                ),
            )

            else -> json(
                newFixedLengthResponse(
                    Response.Status.NOT_FOUND,
                    JSON_MIME_TYPE,
                    JSONObject()
                        .put("error", "not_found")
                        .put("path", session.uri)
                        .toString(),
                ),
            )
        }
    }

    private fun accessibilityService(): DeviceAccessibilityService =
        DeviceAccessibilityService.instance
            ?: throw MissingCapabilityException(
                "accessibility_unavailable",
                "Accessibility service is not enabled.",
            )

    private fun readJsonBody(session: IHTTPSession): JSONObject {
        val files = mutableMapOf<String, String>()
        session.parseBody(files)
        val rawBody = files["postData"].orEmpty()
        return if (rawBody.isBlank()) JSONObject() else JSONObject(rawBody)
    }

    private fun jsonResponse(body: JSONObject): Response =
        json(newFixedLengthResponse(Response.Status.OK, JSON_MIME_TYPE, body.toString()))

    private fun json(response: Response): Response {
        response.addHeader("Content-Type", "application/json; charset=utf-8")
        return response
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

    companion object {
        private const val TAG = "AutoGLM/HTTP"
        private const val DEFAULT_DEVICE_ID = "android-local"
        private const val JSON_MIME_TYPE = "application/json"
    }
}

private class MissingCapabilityException(
    val code: String,
    override val message: String,
) : RuntimeException(message)
