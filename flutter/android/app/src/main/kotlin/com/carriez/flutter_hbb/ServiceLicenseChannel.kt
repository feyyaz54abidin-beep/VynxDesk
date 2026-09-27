package com.carriez.flutter_hbb

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.StandardMethodCodec
import java.io.File
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/** A dedicated signing identity, never an exportable device/HWID secret. */
object ServiceLicenseChannel {
    private const val ALIAS = "vynxdesk.managed-service.p256.v1"
    private val payloadPattern = Regex("VYNXDESK/1\\n(activate|refresh|devices)\\n[A-Za-z0-9_-]{43}\\n[a-f0-9]{64}")
    private val idPattern = Regex("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")

    fun attach(context: Context, engine: FlutterEngine) {
        val app = context.applicationContext
        val messenger = engine.dartExecutor.binaryMessenger
        val channel = MethodChannel(messenger, "com.vynxdesk.client/service-license",
            StandardMethodCodec.INSTANCE, messenger.makeBackgroundTaskQueue())
        channel.setMethodCallHandler { call, result ->
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                result.error("unsupported_android", "Managed device keys require Android 6 or newer", null)
                return@setMethodCallHandler
            }
            try {
                val state = AtomicFile(File(app.noBackupFilesDir, "vynxdesk-service-activation"))
                when (call.method) {
                    "identity" -> {
                        val entry = key()
                        val id = if (state.baseFile.exists()) String(state.readFully(), Charsets.UTF_8) else null
                        result.success(mapOf("public_key" to Base64.encodeToString(entry.certificate.publicKey.encoded, Base64.NO_WRAP),
                            "activation_id" to id?.takeIf { idPattern.matches(it) }))
                    }
                    "sign" -> {
                        val message = call.arguments as? String
                        if (message == null || !payloadPattern.matches(message)) {
                            result.error("invalid_payload", "Invalid service proof", null)
                        } else {
                            val signer = Signature.getInstance("SHA256withECDSA")
                            signer.initSign(key().privateKey)
                            signer.update(message.toByteArray(Charsets.UTF_8))
                            result.success(Base64.encodeToString(signer.sign(), Base64.NO_WRAP))
                        }
                    }
                    "remember" -> {
                        val id = call.arguments as? String
                        if (id == null || !idPattern.matches(id)) {
                            result.error("invalid_activation", "Invalid activation identifier", null)
                        } else {
                            val output = state.startWrite()
                            try {
                                output.write(id.toByteArray(Charsets.UTF_8))
                                state.finishWrite(output)
                            } catch (e: Exception) {
                                state.failWrite(output)
                                throw e
                            }
                            result.success(null)
                        }
                    }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) {
                // Do not log license codes, signed payloads, tokens or key material.
                result.error("device_key_unavailable", "The device signing identity is unavailable", null)
            }
        }
    }

    @Synchronized
    private fun key(): KeyStore.PrivateKeyEntry {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!store.containsAlias(ALIAS)) {
            val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            generator.initialize(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .build())
            generator.generateKeyPair()
        }
        return store.getEntry(ALIAS, null) as KeyStore.PrivateKeyEntry
    }
}
