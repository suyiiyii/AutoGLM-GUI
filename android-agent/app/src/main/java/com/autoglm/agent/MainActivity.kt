package com.autoglm.agent

import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.autoglm.agent.projection.ScreenCaptureController
import com.autoglm.agent.service.AgentForegroundService
import com.autoglm.agent.service.DeviceAccessibilityService

class MainActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var endpointView: TextView
    private lateinit var accessibilityView: TextView
    private lateinit var captureView: TextView
    private lateinit var demoStatusView: TextView

    private val capturePermissionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            Log.i(TAG, "capturePermissionLauncher resultCode=${result.resultCode} hasData=${result.data != null}")
            if (result.resultCode == RESULT_OK && result.data != null) {
                ContextCompat.startForegroundService(
                    this,
                    AgentForegroundService.createEnableCaptureIntent(this),
                )
                completeCaptureGrant(result.resultCode, Intent(result.data!!), retries = 10)
            } else {
                demoStatusView.text = getString(R.string.capture_denied)
                refreshState()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(TAG, "onCreate intent=$intent")
        setContentView(R.layout.activity_main)

        statusView = findViewById(R.id.statusText)
        endpointView = findViewById(R.id.endpointText)
        accessibilityView = findViewById(R.id.accessibilityStatusText)
        captureView = findViewById(R.id.captureStatusText)
        demoStatusView = findViewById(R.id.demoStatusText)

        findViewById<Button>(R.id.startButton).setOnClickListener {
            ContextCompat.startForegroundService(
                this,
                AgentForegroundService.createStartIntent(this),
            )
            refreshState()
        }

        findViewById<Button>(R.id.stopButton).setOnClickListener {
            startService(AgentForegroundService.createStopIntent(this))
            refreshState()
        }

        findViewById<Button>(R.id.accessibilityButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        findViewById<Button>(R.id.captureButton).setOnClickListener {
            requestScreenCapturePermission()
        }

        findViewById<Button>(R.id.tapTargetButton).setOnClickListener {
            demoStatusView.text = getString(R.string.tap_target_hit)
        }

        findViewById<EditText>(R.id.demoInput).setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                demoStatusView.text = getString(R.string.input_focused)
            }
        }

        ensureAgentRunning()
        maybeRequestCapture(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        Log.i(TAG, "onNewIntent intent=$intent")
        setIntent(intent)
        maybeRequestCapture(intent)
    }

    override fun onResume() {
        super.onResume()
        refreshState()
    }

    private fun refreshState() {
        val running = AgentForegroundService.isRunning()
        val port = AgentForegroundService.currentPort()
        statusView.text = getString(
            if (running) R.string.server_status_running else R.string.server_status_stopped,
        )
        endpointView.text = getString(R.string.server_endpoint_template, port)
        accessibilityView.text = getString(
            if (DeviceAccessibilityService.isConnected()) {
                R.string.accessibility_enabled
            } else {
                R.string.accessibility_disabled
            },
        )
        captureView.text = getString(
            if (ScreenCaptureController.hasPermission()) {
                R.string.capture_ready
            } else {
                R.string.capture_missing
            },
        )
    }

    private fun ensureAgentRunning() {
        if (AgentForegroundService.isRunning()) {
            return
        }
        ContextCompat.startForegroundService(
            this,
            AgentForegroundService.createStartIntent(this),
        )
    }

    private fun requestScreenCapturePermission() {
        Log.i(TAG, "requestScreenCapturePermission")
        val manager = getSystemService(MediaProjectionManager::class.java)
        capturePermissionLauncher.launch(manager.createScreenCaptureIntent())
    }

    private fun maybeRequestCapture(intent: Intent?) {
        if (intent?.getBooleanExtra(EXTRA_REQUEST_CAPTURE, false) == true) {
            requestScreenCapturePermission()
        }
    }

    private fun completeCaptureGrant(resultCode: Int, data: Intent, retries: Int) {
        if (!AgentForegroundService.isProjectionModeEnabled()) {
            if (retries <= 0) {
                Log.e(TAG, "completeCaptureGrant timed out waiting for projection mode")
                demoStatusView.text = getString(
                    R.string.capture_failed_template,
                    "foreground service did not enter mediaProjection mode in time.",
                )
                refreshState()
                return
            }
            demoStatusView.postDelayed(
                { completeCaptureGrant(resultCode, Intent(data), retries - 1) },
                100L,
            )
            return
        }

        try {
            ScreenCaptureController.storePermission(this, resultCode, data)
            demoStatusView.text = getString(R.string.capture_granted)
            Log.i(TAG, "completeCaptureGrant success")
        } catch (error: SecurityException) {
            Log.e(TAG, "completeCaptureGrant security failure", error)
            demoStatusView.text = getString(
                R.string.capture_failed_template,
                error.message ?: error.javaClass.simpleName,
            )
        }
        refreshState()
    }

    companion object {
        private const val TAG = "AutoGLM/Main"
        const val EXTRA_REQUEST_CAPTURE = "request_capture"
    }
}
