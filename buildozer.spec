[app]
title = My Kivy Game
package.name = mykivygame
package.domain = org.yourname

# Папка с main.py (мы запускаем buildozer ИЗ my_kivy_game)
source.dir = .

source.include_exts = py,png,jpg,jpeg,gif,kv,atlas,ttf,otf,wav,mp3,ogg

version = 0.1
requirements = python3,kivy

orientation = landscape
fullscreen = 1

android.minapi = 21
android.api = 34
android.ndk_api = 21
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0