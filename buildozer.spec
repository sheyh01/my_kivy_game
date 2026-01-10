[app]
# (str) Title of your application
title = My Kivy Game

# (str) Package name
package.name = my_kivy_game

# (str) Package domain (reverse domain name)
package.domain = org.example

# (list) Source files to include (let empty to include everything)
source.include_exts = py,png,jpg,kv,xml

# (str) Application versioning (may be a number or string)
version = 0.1

# (list) Application requirements
requirements = python3,kivy

# (str) Entry point / main module
# (default is main.py; change only if different)
# entrypoint = main.py

# (list) Permissions
android.permissions = INTERNET

# (int) Target Android API
android.api = 31

# (int) Minimum Android API your app will support
android.minapi = 21

# (str) Android NDK version (if required)
# android.ndk = 23b

# (bool) Use P4A bootstrap (modern builds use "sdl2")
# android.bootstrap = sdl2

# (str) Signing (for release builds)
# android.release_keystore = /path/to/keystore
# android.release_keyalias = mykey
# android.release_keystore_passwd = secret
# android.release_keyalias_passwd = secret

[buildozer]
# (str) buildozer's working directory (default .)
# build_dir = ./.buildozer