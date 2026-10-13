# Proguard rules for vdown app
-keep class com.vdown.app.data.** { *; }
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}
-keep class com.bumptech.glide.** { *; }
-dontwarn com.bumptech.glide.**
