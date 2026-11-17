[app]
package.name = calculator
package.domain = org.test

title = Calculator

version = 1.0.0

source.dir = calc
source.include_exts = py,png,jpg,kv,atlas

requirements = openssl, python3, kivy, sqlite3
orientation = portrait
icon.filename = %(source.dir)s/pics/icon.png
android.accept_sdk_license = True
android.archs = arm64-v8a
p4a.branch = develop
android.api = 36
android.ndk = 28c
