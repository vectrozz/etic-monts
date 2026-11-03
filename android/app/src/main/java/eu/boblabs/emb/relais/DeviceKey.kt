package eu.boblabs.emb.relais

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * The phone's identity: an EC P-256 key pair generated INSIDE the Android
 * Keystore (StrongBox chip when available, otherwise the TEE). The private key
 * can be used to sign but can never be read or exported — not even by this
 * app — so copying the app's data to another device does not copy the right
 * to post messages.
 */
object DeviceKey {
    private const val ALIAS = "emb-relais-device"

    private fun keyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    /** Creates a fresh key (any previous one is destroyed). Returns (base64 SPKI public key, hardware level). */
    fun create(): Pair<String, String> {
        val ks = keyStore()
        if (ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS)
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        fun spec(strongBox: Boolean) = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .apply { if (strongBox && Build.VERSION.SDK_INT >= 28) setIsStrongBoxBacked(true) }
            .build()
        val pair = try {
            generator.initialize(spec(strongBox = true))
            generator.generateKeyPair()
        } catch (e: Exception) {          // StrongBoxUnavailableException → TEE
            generator.initialize(spec(strongBox = false))
            generator.generateKeyPair()
        }
        return Base64.encodeToString(pair.public.encoded, Base64.NO_WRAP) to hardwareLevel()
    }

    fun exists(): Boolean = keyStore().containsAlias(ALIAS)

    fun delete() {
        val ks = keyStore()
        if (ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS)
    }

    private fun privateKey(): PrivateKey =
        (keyStore().getEntry(ALIAS, null) as? KeyStore.PrivateKeyEntry)?.privateKey
            ?: throw IllegalStateException("no device key")

    /** strongbox | tee | software */
    fun hardwareLevel(): String {
        val key = runCatching { privateKey() }.getOrNull() ?: return "software"
        val info = KeyFactory.getInstance(key.algorithm, "AndroidKeyStore").getKeySpec(key, KeyInfo::class.java)
        return if (Build.VERSION.SDK_INT >= 31) {
            when (info.securityLevel) {
                KeyProperties.SECURITY_LEVEL_STRONGBOX -> "strongbox"
                KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "tee"
                else -> "software"
            }
        } else {
            @Suppress("DEPRECATION")
            if (info.isInsideSecureHardware) "tee" else "software"
        }
    }

    /** base64 DER ECDSA-SHA256 signature, computed inside the Keystore. */
    fun sign(data: ByteArray): String {
        val s = Signature.getInstance("SHA256withECDSA")
        s.initSign(privateKey())
        s.update(data)
        return Base64.encodeToString(s.sign(), Base64.NO_WRAP)
    }
}
