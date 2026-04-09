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
import com.autoglm.agent.projection.ScreenshotPayload
import com.autoglm.agent.reverse.ReverseAgentClient
import com.autoglm.agent.reverse.ReverseAgentUiState
import com.autoglm.agent.service.AgentForegroundService
import com.autoglm.agent.service.DeviceAccessibilityService
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var endpointView: TextView
    private lateinit var accessibilityView: TextView
    private lateinit var captureView: TextView
    private lateinit var setupSummaryView: TextView
    private lateinit var setupChecklistStep1View: TextView
    private lateinit var setupChecklistStep2View: TextView
    private lateinit var setupChecklistStep3View: TextView
    private lateinit var setupChecklistStep4View: TextView
    private lateinit var setupChecklistStep5View: TextView
    private lateinit var setupChecklistStep6View: TextView
    private lateinit var setupPrimaryButton: Button
    private lateinit var validationButton: Button
    private lateinit var recoveryMessageView: TextView
    private lateinit var recoveryActionButton: Button
    private lateinit var demoStatusView: TextView
    private lateinit var reverseAgentStatusView: TextView
    private lateinit var reverseAgentDetailView: TextView
    private lateinit var reverseServerInput: EditText
    private lateinit var pairingCodeInput: EditText
    private lateinit var reverseAgentClient: ReverseAgentClient
    private var validationState: SetupValidationState = SetupValidationState.idle()

    private val reverseStateListener: (ReverseAgentUiState) -> Unit = { state ->
        runOnUiThread { renderReverseAgentState(state) }
    }

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
        setupSummaryView = findViewById(R.id.setupSummaryText)
        setupChecklistStep1View = findViewById(R.id.setupChecklistStep1)
        setupChecklistStep2View = findViewById(R.id.setupChecklistStep2)
        setupChecklistStep3View = findViewById(R.id.setupChecklistStep3)
        setupChecklistStep4View = findViewById(R.id.setupChecklistStep4)
        setupChecklistStep5View = findViewById(R.id.setupChecklistStep5)
        setupChecklistStep6View = findViewById(R.id.setupChecklistStep6)
        setupPrimaryButton = findViewById(R.id.setupPrimaryButton)
        validationButton = findViewById(R.id.runValidationButton)
        recoveryMessageView = findViewById(R.id.recoveryMessageText)
        recoveryActionButton = findViewById(R.id.recoveryActionButton)
        demoStatusView = findViewById(R.id.demoStatusText)
        reverseAgentStatusView = findViewById(R.id.reverseAgentStatusText)
        reverseAgentDetailView = findViewById(R.id.reverseAgentDetailText)
        reverseServerInput = findViewById(R.id.reverseServerInput)
        pairingCodeInput = findViewById(R.id.pairingCodeInput)
        reverseAgentClient = ReverseAgentClient.getInstance(this)

        findViewById<Button>(R.id.startButton).setOnClickListener {
            ContextCompat.startForegroundService(
                this,
                AgentForegroundService.createStartIntent(this),
            )
            scheduleRefreshState()
        }

        findViewById<Button>(R.id.stopButton).setOnClickListener {
            startService(AgentForegroundService.createStopIntent(this))
            scheduleRefreshState()
        }

        findViewById<Button>(R.id.accessibilityButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        findViewById<Button>(R.id.captureButton).setOnClickListener {
            requestScreenCapturePermission()
        }

        setupPrimaryButton.setOnClickListener {
            performPrimarySetupAction(reverseAgentClient.currentState())
        }

        validationButton.setOnClickListener {
            runFirstConnectValidation()
        }

        recoveryActionButton.setOnClickListener {
            performRecoveryAction(reverseAgentClient.currentState())
        }

        findViewById<Button>(R.id.pairButton).setOnClickListener {
            triggerPairingClaim()
        }

        findViewById<Button>(R.id.clearPairingButton).setOnClickListener {
            reverseAgentClient.clearPairing()
            validationState = SetupValidationState.idle()
            demoStatusView.text = getString(R.string.reverse_pairing_cleared)
            refreshState()
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
        reverseAgentClient.addListener(reverseStateListener)
        refreshState()
    }

    override fun onPause() {
        reverseAgentClient.removeListener(reverseStateListener)
        super.onPause()
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
        renderReverseAgentState(reverseAgentClient.currentState())
    }

    private fun ensureAgentRunning() {
        if (AgentForegroundService.isRunning()) {
            return
        }
        ContextCompat.startForegroundService(
            this,
            AgentForegroundService.createStartIntent(this),
        )
        scheduleRefreshState()
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

    private fun scheduleRefreshState() {
        window.decorView.postDelayed({ refreshState() }, 300L)
    }

    private fun performPrimarySetupAction(state: ReverseAgentUiState) {
        when (resolvePrimaryAction(state)) {
            SetupAction.START_AGENT -> {
                ContextCompat.startForegroundService(
                    this,
                    AgentForegroundService.createStartIntent(this),
                )
                demoStatusView.text = getString(R.string.setup_action_start_agent)
                scheduleRefreshState()
            }

            SetupAction.OPEN_ACCESSIBILITY -> {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }

            SetupAction.REQUEST_CAPTURE -> {
                requestScreenCapturePermission()
            }

            SetupAction.CLAIM_PAIRING -> {
                triggerPairingClaim()
            }

            SetupAction.RECONNECT_REVERSE -> {
                ContextCompat.startForegroundService(
                    this,
                    AgentForegroundService.createStartIntent(this),
                )
                demoStatusView.text = getString(R.string.setup_action_reconnect)
                scheduleRefreshState()
            }

            SetupAction.RUN_VALIDATION -> runFirstConnectValidation()
            SetupAction.NONE -> Unit
        }
    }

    private fun performRecoveryAction(state: ReverseAgentUiState) {
        when {
            !AgentForegroundService.isRunning() -> performPrimarySetupAction(state)
            !DeviceAccessibilityService.isConnected() -> performPrimarySetupAction(state)
            !ScreenCaptureController.hasPermission() -> performPrimarySetupAction(state)
            state.connectionStatus == "error" -> {
                reverseAgentClient.clearPairing()
                validationState = SetupValidationState.idle()
                demoStatusView.text = getString(R.string.reverse_pairing_cleared)
                refreshState()
            }

            state.connectionStatus == "paired" || state.connectionStatus == "connecting" || state.connectionStatus == "stale" ->
                performPrimarySetupAction(state)

            validationState.status == ValidationStatus.FAILED -> runFirstConnectValidation()
            else -> performPrimarySetupAction(state)
        }
    }

    private fun triggerPairingClaim() {
        validationState = SetupValidationState.idle()
        ContextCompat.startForegroundService(
            this,
            AgentForegroundService.createStartIntent(this),
        )
        reverseAgentClient.pair(
            serverBaseUrl = reverseServerInput.text.toString(),
            pairingCode = pairingCodeInput.text.toString(),
        ) { result ->
            result.onSuccess { session ->
                reverseServerInput.setText(session.serverBaseUrl)
                pairingCodeInput.text?.clear()
                demoStatusView.text = getString(R.string.reverse_pairing_claimed, session.agentId)
                refreshState()
            }.onFailure { error ->
                demoStatusView.text = getString(
                    R.string.reverse_pairing_failed_template,
                    error.message ?: error.javaClass.simpleName,
                )
                refreshState()
            }
        }
    }

    private fun completeCaptureGrant(resultCode: Int, data: Intent, retries: Int) {
        if (!AgentForegroundService.isProjectionModeEnabled()) {
            if (retries <= 0) {
                Log.e(TAG, "completeCaptureGrant timed out waiting for projection mode")
                demoStatusView.text = getString(
                    R.string.capture_failed_template,
                    getString(R.string.capture_foreground_service_timeout),
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

    private fun renderReverseAgentState(state: ReverseAgentUiState) {
        reverseAgentStatusView.text = getString(
            when (state.connectionStatus) {
                "pairing" -> R.string.reverse_status_pairing
                "paired" -> R.string.reverse_status_paired
                "connecting" -> R.string.reverse_status_connecting
                "connected" -> R.string.reverse_status_connected
                "stale" -> R.string.reverse_status_stale
                "error" -> R.string.reverse_status_error
                else -> R.string.reverse_status_unpaired
            },
        )
        reverseAgentDetailView.text = getString(
            R.string.reverse_agent_detail_template,
            state.serverBaseUrl ?: "-",
            state.agentId ?: "-",
            state.pairingId ?: "-",
            state.statusMessage,
        )
        if (reverseServerInput.text.isNullOrBlank() && !state.serverBaseUrl.isNullOrBlank()) {
            reverseServerInput.setText(state.serverBaseUrl)
        }
        renderSetupState(state)
    }

    private fun renderSetupState(state: ReverseAgentUiState) {
        val running = AgentForegroundService.isRunning()
        val accessibilityEnabled = DeviceAccessibilityService.isConnected()
        val captureReady = ScreenCaptureController.hasPermission()
        val pairingClaimed = state.connectionStatus != "unpaired" && state.connectionStatus != "error"
        val reverseConnected = state.connectionStatus == "connected"
        val validationPassed = validationState.status == ValidationStatus.SUCCESS &&
            running && accessibilityEnabled && captureReady && reverseConnected

        setupChecklistStep1View.text = getString(
            if (running) R.string.setup_step_agent_done else R.string.setup_step_agent_pending,
        )
        setupChecklistStep2View.text = getString(
            if (accessibilityEnabled) R.string.setup_step_accessibility_done else R.string.setup_step_accessibility_pending,
        )
        setupChecklistStep3View.text = getString(
            if (captureReady) R.string.setup_step_capture_done else R.string.setup_step_capture_pending,
        )
        setupChecklistStep4View.text = getString(
            if (pairingClaimed) R.string.setup_step_pair_done else R.string.setup_step_pair_pending,
        )
        setupChecklistStep5View.text = getString(
            if (reverseConnected) R.string.setup_step_connect_done else R.string.setup_step_connect_pending,
        )
        setupChecklistStep6View.text = when (validationState.status) {
            ValidationStatus.SUCCESS -> getString(R.string.setup_step_validation_done)
            ValidationStatus.RUNNING -> getString(R.string.validation_running)
            ValidationStatus.FAILED -> getString(
                R.string.recovery_validation_failed_template,
                validationState.message,
            )

            ValidationStatus.IDLE -> getString(R.string.setup_step_validation_pending)
        }

        setupSummaryView.text = getString(
            when {
                validationPassed -> R.string.setup_summary_ready
                validationState.status == ValidationStatus.FAILED -> R.string.setup_summary_validation_failed
                else -> R.string.setup_summary_in_progress
            },
        )

        val nextAction = resolvePrimaryAction(state)
        setupPrimaryButton.text = getString(
            when (nextAction) {
                SetupAction.START_AGENT -> R.string.setup_action_start_agent
                SetupAction.OPEN_ACCESSIBILITY -> R.string.setup_action_enable_accessibility
                SetupAction.REQUEST_CAPTURE -> R.string.setup_action_grant_capture
                SetupAction.CLAIM_PAIRING -> R.string.setup_action_pair
                SetupAction.RECONNECT_REVERSE -> R.string.setup_action_reconnect
                SetupAction.RUN_VALIDATION -> R.string.setup_action_run_validation
                SetupAction.NONE -> R.string.setup_action_done
            },
        )
        setupPrimaryButton.isEnabled = nextAction != SetupAction.NONE && (
            nextAction != SetupAction.CLAIM_PAIRING ||
                (reverseServerInput.text?.isNotBlank() == true && pairingCodeInput.text?.isNotBlank() == true)
            )

        validationButton.isEnabled = running && accessibilityEnabled && captureReady && reverseConnected &&
            validationState.status != ValidationStatus.RUNNING

        recoveryMessageView.text = buildRecoveryMessage(state, running, accessibilityEnabled, captureReady)
        recoveryActionButton.text = getString(
            if (state.connectionStatus == "error") {
                R.string.reverse_clear_pairing_button
            } else {
                R.string.recovery_action_default
            },
        )
    }

    private fun buildRecoveryMessage(
        state: ReverseAgentUiState,
        running: Boolean,
        accessibilityEnabled: Boolean,
        captureReady: Boolean,
    ): String {
        return when {
            !running -> getString(R.string.recovery_agent_missing)
            !accessibilityEnabled -> getString(R.string.recovery_accessibility_missing)
            !captureReady -> getString(R.string.recovery_capture_missing)
            state.connectionStatus == "unpaired" -> getString(R.string.recovery_pairing_missing)
            state.connectionStatus == "paired" || state.connectionStatus == "connecting" || state.connectionStatus == "stale" ->
                getString(R.string.recovery_reverse_connecting)

            state.connectionStatus == "error" -> getString(
                R.string.recovery_reverse_error_template,
                state.statusMessage,
            )

            validationState.status == ValidationStatus.FAILED -> getString(
                R.string.recovery_validation_failed_template,
                validationState.message,
            )

            else -> getString(R.string.recovery_default)
        }
    }

    private fun resolvePrimaryAction(state: ReverseAgentUiState): SetupAction {
        return when {
            !AgentForegroundService.isRunning() -> SetupAction.START_AGENT
            !DeviceAccessibilityService.isConnected() -> SetupAction.OPEN_ACCESSIBILITY
            !ScreenCaptureController.hasPermission() -> SetupAction.REQUEST_CAPTURE
            state.connectionStatus == "unpaired" || state.connectionStatus == "error" -> SetupAction.CLAIM_PAIRING
            state.connectionStatus == "paired" || state.connectionStatus == "connecting" || state.connectionStatus == "stale" ->
                SetupAction.RECONNECT_REVERSE

            validationState.status != ValidationStatus.SUCCESS -> SetupAction.RUN_VALIDATION
            else -> SetupAction.NONE
        }
    }

    private fun runFirstConnectValidation() {
        val state = reverseAgentClient.currentState()
        if (
            !AgentForegroundService.isRunning() ||
            !DeviceAccessibilityService.isConnected() ||
            !ScreenCaptureController.hasPermission() ||
            state.connectionStatus != "connected"
        ) {
            validationState = SetupValidationState.failed(getString(R.string.validation_failure_not_ready))
            refreshState()
            return
        }

        validationState = SetupValidationState.running()
        refreshState()

        thread(name = "autoglm-setup-validation") {
            try {
                val accessibilityService = DeviceAccessibilityService.instance
                    ?: throw IllegalStateException(getString(R.string.validation_failure_accessibility))
                val currentApp = accessibilityService.currentApp()
                val screenshot = ScreenCaptureController.capture(this, 5_000L)
                if (!isPayloadUsable(screenshot)) {
                    throw IllegalStateException(getString(R.string.validation_failure_capture))
                }
                validationState = SetupValidationState.success(
                    getString(
                        R.string.validation_success_template,
                        currentApp,
                        screenshot.width,
                        screenshot.height,
                    ),
                )
                runOnUiThread {
                    demoStatusView.text = validationState.message
                    refreshState()
                }
            } catch (error: Exception) {
                validationState = SetupValidationState.failed(
                    error.message ?: error.javaClass.simpleName,
                )
                runOnUiThread {
                    demoStatusView.text = getString(
                        R.string.recovery_validation_failed_template,
                        validationState.message,
                    )
                    refreshState()
                }
            }
        }
    }

    private fun isPayloadUsable(payload: ScreenshotPayload): Boolean {
        return payload.width > 0 && payload.height > 0 && payload.base64Data.isNotBlank()
    }

    companion object {
        private const val TAG = "AutoGLM/Main"
        const val EXTRA_REQUEST_CAPTURE = "request_capture"
    }
}

private enum class SetupAction {
    START_AGENT,
    OPEN_ACCESSIBILITY,
    REQUEST_CAPTURE,
    CLAIM_PAIRING,
    RECONNECT_REVERSE,
    RUN_VALIDATION,
    NONE,
}

private enum class ValidationStatus {
    IDLE,
    RUNNING,
    SUCCESS,
    FAILED,
}

private data class SetupValidationState(
    val status: ValidationStatus,
    val message: String,
) {
    companion object {
        fun idle(): SetupValidationState = SetupValidationState(
            status = ValidationStatus.IDLE,
            message = "",
        )

        fun running(): SetupValidationState = SetupValidationState(
            status = ValidationStatus.RUNNING,
            message = "",
        )

        fun success(message: String): SetupValidationState = SetupValidationState(
            status = ValidationStatus.SUCCESS,
            message = message,
        )

        fun failed(message: String): SetupValidationState = SetupValidationState(
            status = ValidationStatus.FAILED,
            message = message,
        )
    }
}
