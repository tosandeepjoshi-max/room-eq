"""Build and sign Sleep Home (no Gradle): aapt2, javac, d8, zipalign, apksigner.

  .venv\\Scripts\\python shield\\sleephome\\build.py        # writes shield/sleephome/build/sleephome.apk

Needs JDK 17 (Microsoft.OpenJDK.17) and the Android SDK in %LOCALAPPDATA%\\Android\\Sdk with
build-tools;34.0.0 and platforms;android-30. Signs with the standard debug key
(~/.android/debug.keystore, made here if missing): keep that file, or a later install over the
old app fails and needs an uninstall first.
"""
import glob
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "build"
SDK = Path(os.environ.get("ANDROID_HOME", Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"))
TOOLS = SDK / "build-tools" / "34.0.0"
ANDROID_JAR = SDK / "platforms" / "android-30" / "android.jar"
JDK = Path(os.environ.get("JAVA_HOME") or glob.glob(r"C:\Program Files\Microsoft\jdk-17*")[0])
KEYSTORE = Path.home() / ".android" / "debug.keystore"


def run(*cmd):
    env = dict(os.environ, JAVA_HOME=str(JDK), PATH=f"{JDK / 'bin'};{os.environ['PATH']}")
    subprocess.run([str(c) for c in cmd], check=True, env=env)


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "gen").mkdir(parents=True)
    (OUT / "classes").mkdir()
    (OUT / "dex").mkdir()

    run(TOOLS / "aapt2.exe", "compile", "--dir", HERE / "res", "-o", OUT / "res.zip")
    run(TOOLS / "aapt2.exe", "link", "-I", ANDROID_JAR, "--manifest", HERE / "AndroidManifest.xml",
        "--min-sdk-version", "26", "--target-sdk-version", "30",
        "--java", OUT / "gen", "-o", OUT / "unsigned.apk", OUT / "res.zip")

    sources = list((HERE / "src").rglob("*.java")) + list((OUT / "gen").rglob("*.java"))
    run(JDK / "bin" / "javac.exe", "--release", "8", "-classpath", ANDROID_JAR,
        "-d", OUT / "classes", *sources)
    run(TOOLS / "d8.bat", "--lib", ANDROID_JAR, "--min-api", "26", "--output", OUT / "dex",
        *(OUT / "classes").rglob("*.class"))
    with zipfile.ZipFile(OUT / "unsigned.apk", "a") as apk:
        apk.write(OUT / "dex" / "classes.dex", "classes.dex")

    run(TOOLS / "zipalign.exe", "-f", "4", OUT / "unsigned.apk", OUT / "aligned.apk")
    if not KEYSTORE.exists():
        KEYSTORE.parent.mkdir(exist_ok=True)
        run(JDK / "bin" / "keytool.exe", "-genkeypair", "-keystore", KEYSTORE, "-storepass", "android",
            "-alias", "androiddebugkey", "-keypass", "android", "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "10000", "-dname", "CN=Android Debug,O=Android,C=US")
    run(TOOLS / "apksigner.bat", "sign", "--ks", KEYSTORE, "--ks-pass", "pass:android",
        "--out", OUT / "sleephome.apk", OUT / "aligned.apk")
    print(f"Built {OUT / 'sleephome.apk'}")


if __name__ == "__main__":
    main()
