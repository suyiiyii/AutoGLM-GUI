plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.rikka.tools.materialthemebuilder")
}

android {
    namespace = "com.autoglm.agent"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.autoglm.agent"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("org.nanohttpd:nanohttpd:2.3.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}

materialThemeBuilder {
    themes {
        create("AutoGLMAgent") {
            primaryColor = "#3F51B5"
            lightThemeFormat = "Theme.Material3.Light.%s"
            lightThemeParent = "Theme.Material3.Light.NoActionBar"
            darkThemeFormat = "Theme.Material3.Dark.%s"
            darkThemeParent = "Theme.Material3.Dark.NoActionBar"
        }
    }
    generatePalette = true
    generateTextColors = true
}
