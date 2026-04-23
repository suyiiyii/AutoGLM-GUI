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
import android.util.Log
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

object ScreenCaptureController {
    private val stateLock = Any()
    private val captureLock = ReentrantLock()

    @Volatile
    private var mediaProjection: MediaProjection? = null

    @Volatile
    private var hasPermission: Boolean = false

    @Volatile
    private var projectionGeneration: Long = 0L

    private val workerThread = HandlerThread("autoglm-screen-capture").apply { start() }
    private val workerHandler = Handler(workerThread.looper)

    private var imageReader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var lastPayload: ScreenshotPayload? = null

    fun hasPermission(): Boolean = hasPermission

    fun storePermission(context: Context, resultCode: Int, data: Intent) {
        synchronized(stateLock) {
            val manager = context.getSystemService(MediaProjectionManager::class.java)
            val nextGeneration = projectionGeneration + 1L
            Log.i(
                TAG,
                "storePermission begin generation=$nextGeneration resultCode=$resultCode hasExisting=${mediaProjection != null}",
            )
            projectionGeneration = nextGeneration
            releaseProjectionResourcesLocked()
            hasPermission = false

            val projection = manager.getMediaProjection(resultCode, Intent(data))
            projection.registerCallback(
                object : MediaProjection.Callback() {
                    override fun onStop() {
                        Log.w(TAG, "projection onStop generation=$nextGeneration currentGeneration=$projectionGeneration")
                        synchronized(stateLock) {
                            if (projectionGeneration == nextGeneration) {
                                releaseProjectionResourcesLocked()
                                hasPermission = false
                            }
                        }
                    }
                },
                workerHandler,
            )

            val metrics = context.resources.displayMetrics
            val width = metrics.widthPixels
            val height = metrics.heightPixels
            val densityDpi = metrics.densityDpi
            val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
            val display = projection.createVirtualDisplay(
                "AutoGLMAndroidAgentCapture",
                width,
                height,
                densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.surface,
                null,
                workerHandler,
            )

            mediaProjection = projection
            imageReader = reader
            virtualDisplay = display
            lastPayload = null
            hasPermission = true
            Log.i(
                TAG,
                "storePermission success generation=$nextGeneration hasPermission=$hasPermission width=$width height=$height",
            )
        }
    }

    fun capture(context: Context, timeoutMs: Long): ScreenshotPayload {
        return captureLock.withLock {
            val session = synchronized(stateLock) {
                val projection = mediaProjection ?: throw IllegalStateException(
                    "Screen capture permission has not been granted.",
                )
                val reader = imageReader ?: throw IllegalStateException(
                    "Screen capture session is not initialized.",
                )
                val display = virtualDisplay ?: throw IllegalStateException(
                    "Virtual display is not initialized.",
                )
                val metrics = context.resources.displayMetrics
                Log.i(
                    TAG,
                    "capture begin timeoutMs=$timeoutMs generation=$projectionGeneration hasPermission=$hasPermission projection=$projection display=$display",
                )
                CaptureSession(
                    imageReader = reader,
                    width = metrics.widthPixels,
                    height = metrics.heightPixels,
                    generation = projectionGeneration,
                )
            }

            var image: Image? = null
            val latch = CountDownLatch(1)

            try {
                image = session.imageReader.acquireLatestImage()
                if (image == null) {
                    session.imageReader.setOnImageAvailableListener(
                        { reader ->
                            image = reader.acquireLatestImage()
                            if (image != null) {
                                latch.countDown()
                            }
                        },
                        workerHandler,
                    )
                    if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) {
                        val cachedPayload = synchronized(stateLock) { lastPayload }
                        if (cachedPayload != null) {
                            Log.w(
                                TAG,
                                "capture timed out, returning cached frame timeoutMs=$timeoutMs generation=${session.generation}",
                            )
                            return cachedPayload
                        }
                        Log.e(TAG, "capture timed out timeoutMs=$timeoutMs generation=${session.generation}")
                        throw IllegalStateException("Timed out while capturing screenshot.")
                    }
                }
                val capturedImage = image ?: throw IllegalStateException("No image available.")
                val payload = capturedImage.toPayload(session.width, session.height)
                synchronized(stateLock) {
                    lastPayload = payload
                }
                Log.i(
                    TAG,
                    "capture success width=${session.width} height=${session.height} generation=${session.generation}",
                )
                payload
            } finally {
                image?.close()
                session.imageReader.setOnImageAvailableListener(null, null)
                Log.i(TAG, "capture cleanup complete generation=${session.generation}")
            }
        }
    }

    private fun releaseProjectionResourcesLocked() {
        imageReader?.setOnImageAvailableListener(null, null)
        imageReader?.close()
        imageReader = null

        virtualDisplay?.release()
        virtualDisplay = null

        mediaProjection?.stop()
        mediaProjection = null
        lastPayload = null
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

    private data class CaptureSession(
        val imageReader: ImageReader,
        val width: Int,
        val height: Int,
        val generation: Long,
    )
}

data class ScreenshotPayload(
    val base64Data: String,
    val width: Int,
    val height: Int,
)

private const val TAG = "AutoGLM/Capture"
