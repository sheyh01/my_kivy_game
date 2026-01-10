[app]
title = My Kivy Game
package.name = mykivygame
package.domain = org.yourname

source.dir = .
source.include_exts = py,png,jpg,jpeg,gif,kv,atlas,ttf,otf,wav,mp3,ogg

version = 0.1

requirements = python3,kivy

# (не обязательно) иконка:
# icon.filename = %(source.dir)s/icon.png

orientation = landscape
fullscreen = 1

# если нужны разрешения — добавишь позже, сейчас лучше без них
android.permissions =

# Отключим ненужные файлы из сборки
source.exclude_exts = pyc,pyo
source.exclude_dirs = __pycache__,.git,.idea,.vscode,tests

# -------- Android --------
android.minapi = 21
android.api = 34
android.ndk_api = 21
android.archs = arm64-v8a,armeabi-v7a

# Для CI (GitHub Actions) удобно, чтобы лицензии принимались автоматически
android.accept_sdk_license = True

# Release подпись (заполним через CI/вручную позже)
android.release_keystore =
android.release_keystore_passwd =
android.release_keyalias =
android.release_keyalias_passwd =

[buildozer]
log_level = 2
warn_on_root = 0