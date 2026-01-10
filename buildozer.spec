[app]
# Название игры (как будет отображаться на телефоне)
title = My Kivy Game

# Внутреннее имя пакета (ТОЛЬКО маленькие буквы/цифры/подчёркивания, без пробелов!)
package.name = mykivygame

# Обратный домен (можешь поменять на свой ник)
package.domain = org.yourname

# <<< ЭТО ГЛАВНОЕ, ЧЕГО НЕ ХВАТАЕТ >>>
# Папка, где лежит main.py (точка = текущая папка)
source.dir = .

# Какие расширения файлов включать в APK
source.include_exts = py,png,jpg,jpeg,gif,kv,atlas,ttf,otf,wav,mp3,ogg

# Версия приложения
version = 0.1

# Python-библиотеки
requirements = python3,kivy

# Настройки экрана
orientation = landscape
fullscreen = 1

# Пока без разрешений
android.permissions =

# Android-часть (можно оставить так)
android.minapi = 21
android.api = 34
android.ndk_api = 21
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True


[buildozer]
log_level = 2
warn_on_root = 0