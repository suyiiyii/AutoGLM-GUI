package com.autoglm.agent

import android.content.Intent
import android.content.res.ColorStateList
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.core.widget.TextViewCompat
import com.google.android.material.card.MaterialCardView
import com.google.android.material.color.MaterialColors
import com.google.android.material.color.DynamicColors
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
    private lateinit var setupChecklistStep1Card: MaterialCardView
    private lateinit var setupChecklistStep2Card: MaterialCardView
    private lateinit var setupChecklistStep3Card: MaterialCardView
    private lateinit var setupChecklistStep4Card: MaterialCardView
    private lateinit var setupChecklistStep5Card: MaterialCardView
    private lateinit var setupChecklistStep6Card: MaterialCardView
    private lateinit var setupChecklistStep1TitleView: TextView
    private lateinit var setupChecklistStep2TitleView: TextView
    private lateinit var setupChecklistStep3TitleView: TextView
    private lateinit var setupChecklistStep4TitleView: TextView
    private lateinit var setupChecklistStep5TitleView: TextView
    private lateinit var setupChecklistStep6TitleView: TextView
    private lateinit var setupChecklistStep1StatusView: TextView
    private lateinit var setupChecklistStep2StatusView: TextView
    private lateinit var setupChecklistStep3StatusView: TextView
    private lateinit var setupChecklistStep4StatusView: TextView
    private lateinit var setupChecklistStep5StatusView: TextView
    private lateinit var setupChecklistStep6StatusView: TextView
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
        DynamicColors.applyToActivityIfAvailable(this)
        super.onCreate(savedInstanceState)
        Log.i(TAG, "onCreate intent=$intent")
        setContentView(R.layout.activity_main)

        statusView = findViewById(R.id.statusText)
        endpointView = findViewById(R.id.endpointText)
        accessibilityView = findViewById(R.id.accessibilityStatusText)
        captureView = findViewById(R.id.captureStatusText)
        setupSummaryView = findViewById(R.id.setupSummaryText)
        setupChecklistStep1Card = findViewById(R.id.setupChecklistCard1)
        setupChecklistStep2Card = findViewById(R.id.setupChecklistCard2)
        setupChecklistStep3Card = findViewById(R.id.setupChecklistCard3)
        setupChecklistStep4Card = findViewById(R.id.setupChecklistCard4)
        setupChecklistStep5Card = findViewById(R.id.setupChecklistCard5)
        setupChecklistStep6Card = findViewById(R.id.setupChecklistCard6)
        setupChecklistStep1TitleView = findViewById(R.id.setupChecklistStep1Title)
        setupChecklistStep2TitleView = findViewById(R.id.setupChecklistStep2Title)
        setupChecklistStep3TitleView = findViewById(R.id.setupChecklistStep3Title)
        setupChecklistStep4TitleView = findViewById(R.id.setupChecklistStep4Title)
        setupChecklistStep5TitleView = findViewById(R.id.setupChecklistStep5Title)
        setupChecklistStep6TitleView = findViewById(R.id.setupChecklistStep6Title)
        setupChecklistStep1StatusView = findViewById(R.id.setupChecklistStep1Status)
        setupChecklistStep2StatusView = findViewById(R.id.setupChecklistStep2Status)
        setupChecklistStep3StatusView = findViewById(R.id.setupChecklistStep3Status)
        setupChecklistStep4StatusView = findViewById(R.id.setupChecklistStep4Status)
        setupChecklistStep5StatusView = findViewById(R.id.setupChecklistStep5Status)
        setupChecklistStep6StatusView = findViewById(R.id.setupChecklistStep6Status)
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

        val developerSection = findViewById<View>(R.id.developerSection)
        findViewById<Button>(R.id.developerToggleButton).setOnClickListener { toggle ->
            val show = developerSection.visibility != View.VISIBLE
            developerSection.visibility = if (show) View.VISIBLE else View.GONE
            (toggle as Button).setText(
                if (show) R.string.developer_options_hide else R.string.developer_options_show
            )
        }

        findViewById<EditText>(R.id.demoInput).setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) {
                demoStatusView.text = getString(R.string.input_focused)
            }
        }

        ensureAgentRunning()
        maybeRequestCapture(intent)
        maybeAutoPairForTest(intent)
        applyWindowInsets()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        Log.i(TAG, "onNewIntent intent=$intent")
        setIntent(intent)
        maybeRequestCapture(intent)
        maybeAutoPairForTest(intent)
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

    /**
     * Debug-only hook for automated end-to-end tests: when the launching intent
     * carries [EXTRA_TEST_SERVER_URL] and [EXTRA_TEST_PAIRING_CODE], pre-fill the
     * reverse-pairing inputs and claim the pairing without driving the UI.
     * Ignored entirely on non-debuggable (release) builds.
     */
    private fun maybeAutoPairForTest(intent: Intent?) {
        val debuggable =
            (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        if (!debuggable || intent == null) return
        val serverUrl = intent.getStringExtra(EXTRA_TEST_SERVER_URL)
        val pairingCode = intent.getStringExtra(EXTRA_TEST_PAIRING_CODE)
        if (serverUrl.isNullOrBlank() || pairingCode.isNullOrBlank()) return
        Log.i(TAG, "maybeAutoPairForTest injecting server=$serverUrl")
        reverseServerInput.setText(serverUrl)
        pairingCodeInput.setText(pairingCode)
        triggerPairingClaim()
    }

    private fun scheduleRefreshState() {
        window.decorView.postDelayed({ refreshState() }, 300L)
    }

    private fun applyWindowInsets() {
        val rootScrollView = findViewById<View>(R.id.rootScrollView)
        val topAppBar = findViewById<View>(R.id.topAppBar)
        val initialToolbarPaddingTop = topAppBar.paddingTop
        ViewCompat.setOnApplyWindowInsetsListener(rootScrollView) { _, insets ->
            val statusInsets = insets.getInsets(WindowInsetsCompat.Type.statusBars())
            topAppBar.updatePadding(top = initialToolbarPaddingTop + statusInsets.top)
            insets
        }
        ViewCompat.requestApplyInsets(rootScrollView)
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
        val nextAction = resolvePrimaryAction(state)

        renderStepItem(
            card = setupChecklistStep1Card,
            titleView = setupChecklistStep1TitleView,
            statusView = setupChecklistStep1StatusView,
            titleRes = R.string.setup_step_agent_title,
            isDone = running,
            isCurrent = nextAction == SetupAction.START_AGENT,
            currentStatusRes = R.string.setup_step_status_next,
        )
        renderStepItem(
            card = setupChecklistStep2Card,
            titleView = setupChecklistStep2TitleView,
            statusView = setupChecklistStep2StatusView,
            titleRes = R.string.setup_step_accessibility_title,
            isDone = accessibilityEnabled,
            isCurrent = nextAction == SetupAction.OPEN_ACCESSIBILITY,
            currentStatusRes = R.string.setup_step_status_next,
        )
        renderStepItem(
            card = setupChecklistStep3Card,
            titleView = setupChecklistStep3TitleView,
            statusView = setupChecklistStep3StatusView,
            titleRes = R.string.setup_step_capture_title,
            isDone = captureReady,
            isCurrent = nextAction == SetupAction.REQUEST_CAPTURE,
            currentStatusRes = R.string.setup_step_status_next,
        )
        renderStepItem(
            card = setupChecklistStep4Card,
            titleView = setupChecklistStep4TitleView,
            statusView = setupChecklistStep4StatusView,
            titleRes = R.string.setup_step_pair_title,
            isDone = pairingClaimed,
            isCurrent = nextAction == SetupAction.CLAIM_PAIRING,
            currentStatusRes = R.string.setup_step_status_next,
        )
        renderStepItem(
            card = setupChecklistStep5Card,
            titleView = setupChecklistStep5TitleView,
            statusView = setupChecklistStep5StatusView,
            titleRes = R.string.setup_step_connect_title,
            isDone = reverseConnected,
            isCurrent = nextAction == SetupAction.RECONNECT_REVERSE,
            currentStatusRes = R.string.setup_step_status_waiting,
        )
        renderValidationStep(nextAction)

        setupSummaryView.text = getString(
            when {
                validationPassed -> R.string.setup_summary_ready
                validationState.status == ValidationStatus.FAILED -> R.string.setup_summary_validation_failed
                else -> R.string.setup_summary_in_progress
            },
        )

        setupPrimaryButton.text = getString(if (nextAction == SetupAction.NONE) R.string.setup_action_done else R.string.setup_action_continue)
        setupPrimaryButton.isEnabled = nextAction != SetupAction.NONE && (
            nextAction != SetupAction.CLAIM_PAIRING ||
                (reverseServerInput.text?.isNotBlank() == true && pairingCodeInput.text?.isNotBlank() == true)
            )

        validationButton.isEnabled = running && accessibilityEnabled && captureReady && reverseConnected &&
            validationState.status != ValidationStatus.RUNNING
        validationButton.visibility = if (nextAction == SetupAction.RUN_VALIDATION || validationState.status == ValidationStatus.FAILED) {
            View.VISIBLE
        } else {
            View.GONE
        }

        recoveryMessageView.text = buildRecoveryMessage(state, running, accessibilityEnabled, captureReady)
        recoveryActionButton.text = getString(
            if (state.connectionStatus == "error") {
                R.string.reverse_clear_pairing_button
            } else {
                R.string.recovery_action_default
            },
        )
    }

    private fun renderValidationStep(nextAction: SetupAction) {
        setupChecklistStep6TitleView.text = getString(R.string.setup_step_validation_title)
        when (validationState.status) {
            ValidationStatus.SUCCESS -> renderStepItem(
                card = setupChecklistStep6Card,
                titleView = setupChecklistStep6TitleView,
                statusView = setupChecklistStep6StatusView,
                titleRes = R.string.setup_step_validation_title,
                isDone = true,
                isCurrent = false,
                currentStatusRes = R.string.setup_step_status_done,
            )

            ValidationStatus.RUNNING -> renderStepItem(
                card = setupChecklistStep6Card,
                titleView = setupChecklistStep6TitleView,
                statusView = setupChecklistStep6StatusView,
                titleRes = R.string.setup_step_validation_title,
                isDone = false,
                isCurrent = true,
                currentStatusRes = R.string.setup_step_status_check,
            )

            ValidationStatus.FAILED -> renderStepItem(
                card = setupChecklistStep6Card,
                titleView = setupChecklistStep6TitleView,
                statusView = setupChecklistStep6StatusView,
                titleRes = R.string.setup_step_validation_title,
                isDone = false,
                isCurrent = true,
                currentStatusRes = R.string.setup_step_status_check,
            )

            ValidationStatus.IDLE -> renderStepItem(
                card = setupChecklistStep6Card,
                titleView = setupChecklistStep6TitleView,
                statusView = setupChecklistStep6StatusView,
                titleRes = R.string.setup_step_validation_title,
                isDone = false,
                isCurrent = nextAction == SetupAction.RUN_VALIDATION,
                currentStatusRes = R.string.setup_step_status_check,
            )
        }
    }

    private fun renderStepItem(
        card: MaterialCardView,
        titleView: TextView,
        statusView: TextView,
        titleRes: Int,
        isDone: Boolean,
        isCurrent: Boolean,
        currentStatusRes: Int,
    ) {
        val surfaceTransparent = ContextCompat.getColor(this, android.R.color.transparent)
        val doneTokenBackground = MaterialColors.getColor(
            statusView,
            com.google.android.material.R.attr.colorSurfaceContainerHigh,
        )
        titleView.text = getString(titleRes)
        when {
            isDone -> {
                card.setCardBackgroundColor(surfaceTransparent)
                statusView.visibility = View.VISIBLE
                statusView.text = getString(R.string.setup_step_status_done)
                statusView.setTextColor(MaterialColors.getColor(statusView, com.google.android.material.R.attr.colorOnSurfaceVariant))
                statusView.backgroundTintList = ColorStateList.valueOf(doneTokenBackground)
            }

            isCurrent -> {
                card.setCardBackgroundColor(surfaceTransparent)
                statusView.visibility = View.VISIBLE
                statusView.text = getString(currentStatusRes)
                statusView.setTextColor(MaterialColors.getColor(statusView, com.google.android.material.R.attr.colorPrimary))
                statusView.backgroundTintList = null
            }

            else -> {
                card.setCardBackgroundColor(surfaceTransparent)
                statusView.visibility = View.GONE
                statusView.backgroundTintList = null
            }
        }
        TextViewCompat.setTextAppearance(
            titleView,
            if (isCurrent) R.style.StepTitleActive else R.style.StepTitle,
        )
        titleView.setTextColor(
            MaterialColors.getColor(
                titleView,
                when {
                    isCurrent || isDone -> com.google.android.material.R.attr.colorOnSurface
                    else -> com.google.android.material.R.attr.colorOnSurfaceVariant
                },
            ),
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
        // Debug-only test hooks: let CI inject pairing without driving the UI.
        // Only honored in debuggable builds (see maybeAutoPairForTest).
        const val EXTRA_TEST_SERVER_URL = "test_server_url"
        const val EXTRA_TEST_PAIRING_CODE = "test_pairing_code"
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
