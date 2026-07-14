package com.autoglm.agent.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Bundle
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class DeviceAccessibilityService : AccessibilityService() {
    @Volatile
    private var lastPackageName: String = "unknown"

    override fun onServiceConnected() {
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) {
            instance = null
        }
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val pkg = event?.packageName?.toString()
        if (!pkg.isNullOrBlank()) {
            lastPackageName = pkg
        }
    }

    override fun onInterrupt() = Unit

    fun currentApp(): String {
        val rootPackage = rootInActiveWindow?.packageName?.toString()
        return rootPackage ?: lastPackageName
    }

    fun tap(x: Int, y: Int): Boolean = dispatchGestureBlocking(
        GestureDescription.Builder()
            .addStroke(
                GestureDescription.StrokeDescription(
                    Path().apply { moveTo(x.toFloat(), y.toFloat()) },
                    0,
                    80,
                ),
            )
            .build(),
    )

    fun swipe(
        startX: Int,
        startY: Int,
        endX: Int,
        endY: Int,
        durationMs: Long,
    ): Boolean = dispatchGestureBlocking(
        GestureDescription.Builder()
            .addStroke(
                GestureDescription.StrokeDescription(
                    Path().apply {
                        moveTo(startX.toFloat(), startY.toFloat())
                        lineTo(endX.toFloat(), endY.toFloat())
                    },
                    0,
                    durationMs,
                ),
            )
            .build(),
    )

    fun typeText(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: findEditableNode(root)
        val target = focused ?: return false
        val args = Bundle().apply {
            putCharSequence(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                text,
            )
        }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findEditableNode(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable) {
            return node
        }
        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            val match = findEditableNode(child)
            if (match != null) {
                return match
            }
        }
        return null
    }

    private fun dispatchGestureBlocking(gesture: GestureDescription): Boolean {
        val latch = CountDownLatch(1)
        var success = false
        val callback = object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                success = true
                latch.countDown()
            }

            override fun onCancelled(gestureDescription: GestureDescription?) {
                success = false
                latch.countDown()
            }
        }
        if (!dispatchGesture(gesture, callback, null)) {
            return false
        }
        latch.await(3, TimeUnit.SECONDS)
        SystemClock.sleep(250)
        return success
    }

    companion object {
        @Volatile
        var instance: DeviceAccessibilityService? = null
            private set

        fun isConnected(): Boolean = instance != null
    }
}
