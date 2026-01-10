from kivy.core.audio import SoundLoader
import os

print("cwd:", os.getcwd())

path = "assets/snd_pickup.mp3"  # или любой другой твой файл
print("exists:", os.path.exists(path))

snd = SoundLoader.load(path)
print("SoundLoader returned:", snd)

if snd:
    print("Playing...")
    snd.play()
else:
    print("Звук не загрузился (None)")