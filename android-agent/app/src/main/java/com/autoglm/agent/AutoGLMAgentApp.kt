package com.autoglm.agent

import android.app.Application
import com.google.android.material.color.DynamicColors

class AutoGLMAgentApp : Application() {
    override fun onCreate() {
        super.onCreate()
        DynamicColors.applyToActivitiesIfAvailable(this)
    }
}
