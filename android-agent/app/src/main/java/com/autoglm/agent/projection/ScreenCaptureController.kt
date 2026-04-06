package com.autoglm.agent.projection

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.HandlerThread
import android.util.Base64
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

object ScreenCaptureController {
    @Volatile
    private var mediaProjection: MediaProjection? = null

    @Volatile
    private var hasPermission: Boolean = false

    @Volatile
    private var projectionGeneration: Long = 0L

    private val workerThread = HandlerThread("autoglm-screen-capture").apply { start() }
    private val workerHandler = Handler(workerThread.looper)

    fun hasPermission(): Boolean = hasPermission

    fun storePermission(context: Context, resultCode: Int, data: Intent) {
        val manager = context.getSystemService(MediaProjectionManager::class.java)
        val nextGeneration = projectionGeneration + 1L
        projectionGeneration = nextGeneration
        val previousProjection = mediaProjection
        mediaProjection = null
        hasPermission = false
        previousProjection?.stop()

        mediaProjection = manager.getMediaProjection(resultCode, Intent(data)).also { projection ->
            projection.registerCallback(
                object : MediaProjection.Callback() {
                    override fun onStop() {
                        if (projectionGeneration == nextGeneration) {
                            mediaProjection = null
                            hasPermission = false
                        }
                    }
                },
                workerHandler,
            )
        }
        hasPermission = true
    }

    fun capture(context: Context, timeoutMs: Long): ScreenshotPayload {
        val projection = mediaProjection ?: throw IllegalStateException(
            "Screen capture permission has not been granted.",
        )
        val metrics = context.resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val densityDpi = metrics.densityDpi

        val imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        var virtualDisplay: VirtualDisplay? = null
        var image: Image? = null
        val latch = CountDownLatch(1)

        try {
            imageReader.setOnImageAvailableListener(
                { reader ->
                    image = reader.acquireLatestImage()
                    latch.countDown()
                },
                workerHandler,
            )
            virtualDisplay = projection.createVirtualDisplay(
                "AutoGLMAndroidAgentCapture",
                width,
                height,
                densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                imageReader.surface,
                null,
                workerHandler,
            )
            if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) {
                throw IllegalStateException("Timed out while capturing screenshot.")
            }
            val capturedImage = image ?: throw IllegalStateException("No image available.")
            return capturedImage.toPayload(width, height)
        } finally {
            image?.close()
            imageReader.setOnImageAvailableListener(null, null)
            imageReader.close()
            virtualDisplay?.release()
        }
    }

    private fun Image.toPayload(width: Int, height: Int): ScreenshotPayload {
        val plane = planes[0]
        val buffer = plane.buffer
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val rowPadding = rowStride - pixelStride * width
        val bitmap = Bitmap.createBitmap(
            width + rowPadding / pixelStride,
            height,
            Bitmap.Config.ARGB_8888,
        )
        bitmap.copyPixelsFromBuffer(buffer)
        val cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height)
        val output = ByteArrayOutputStream()
        cropped.compress(Bitmap.CompressFormat.PNG, 100, output)
        bitmap.recycle()
        cropped.recycle()
        return ScreenshotPayload(
            base64Data = Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP),
            width = width,
            height = height,
        )
    }
}

data class ScreenshotPayload(
    val base64Data: String,
    val width: Int,
    val height: Int,
)
