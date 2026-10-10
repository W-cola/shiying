"""Build a native universal APK with the official Android SDK, without Gradle downloads."""
import hashlib
import json
import os
import secrets
import subprocess
import zipfile
from pathlib import Path

root=Path(os.environ.get('SHIYING_BUILD_ROOT',str(Path(__file__).resolve().parents[2])))
android=root/'android'
tools_root=root/'.android-build'
sdk=Path(os.environ.get('SHIYING_SDK',str(tools_root/'sdk')))
jdk=Path(os.environ.get('SHIYING_JDK','D:/PyCharm 2026.1.1/jbr'))
build_tools=sdk/'build-tools'/'35.0.1'
android_jar=sdk/'platforms'/'android-35'/'android.jar'
work=tools_root/'app-build'
classes=work/'classes'; generated=work/'generated'; dex=work/'dex'
for p in (classes,generated,dex): p.mkdir(parents=True,exist_ok=True)
env=os.environ.copy(); env.update(JAVA_HOME=str(jdk),TEMP=str(root/'.tmp'),TMP=str(root/'.tmp'))
def run(args):
    # Some Windows SDK binaries don't accept non-ASCII absolute paths.
    # Their input paths stay relative to the existing workspace.
    converted=[str(args[0])]
    for a in args[1:]:
        converted.append(a.relative_to(root).as_posix() if isinstance(a,Path) and a.is_relative_to(root) else str(a))
    subprocess.run(converted,env=env,check=True,cwd=root)

source=android/'app'/'src'/'main'
manifest=work/'AndroidManifest.xml'
manifest.write_text((source/'AndroidManifest.xml').read_text(encoding='utf-8').replace('<manifest ','<manifest package="cn.shiying.mobile" ',1),encoding='utf-8')
print('Compiling Android resources...',flush=True)
run([build_tools/'aapt2.exe','compile','--dir',source/'res','-o',work/'resources.zip'])
run([build_tools/'aapt2.exe','link','-o',work/'resources.apk','-I',android_jar,'--manifest',manifest,
     '--java',generated,'--min-sdk-version','26','--target-sdk-version','35','-A',source/'assets',work/'resources.zip'])
sources=[*source.joinpath('java').rglob('*.java'),*generated.rglob('*.java')]
print('Compiling native application...',flush=True)
for folder,pattern in ((classes,'*.class'),(dex,'*.dex')):
    for stale in folder.rglob(pattern):
        if not stale.resolve().is_relative_to(folder.resolve()): raise RuntimeError('Compiled output escaped the build directory')
        stale.unlink()
argfile=work/'javac-args.txt'
args=['--release','8','-encoding','UTF-8','-classpath',str(android_jar),'-d',str(classes),*map(str,sources)]
argfile.write_text('\n'.join('"'+a.replace('\\','/')+'"' for a in args),encoding='utf-8')
run([jdk/'bin'/'javac.exe','@'+str(argfile)])
jar=work/'app-classes.jar'
with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as bundle:
    for f in classes.rglob('*.class'): bundle.write(f,f.relative_to(classes).as_posix())
run([jdk/'bin'/'java.exe','-cp',build_tools/'lib'/'d8.jar','com.android.tools.r8.D8',
     '--release','--min-api','26','--lib',android_jar,'--output',dex,jar])
unsigned=work/'unsigned.apk'
with zipfile.ZipFile(work/'resources.apk') as resources,zipfile.ZipFile(unsigned,'w') as bundle:
    for info in resources.infolist(): bundle.writestr(info,resources.read(info))
    for f in dex.glob('*.dex'): bundle.write(f,f.name,compress_type=zipfile.ZIP_STORED)
aligned=work/'aligned.apk'
run([build_tools/'zipalign.exe','-f','-p','4',unsigned,aligned])
private=tools_root/'private'; private.mkdir(exist_ok=True)
key=private/'shiying-release.jks'; password=private/'signing-password.txt'
if not password.exists(): password.write_text(secrets.token_urlsafe(32),encoding='utf-8')
env['SHIYING_KEY_PASSWORD']=password.read_text(encoding='utf-8')
if not key.exists():
    run([jdk/'bin'/'keytool.exe','-genkeypair','-keystore',key,'-alias','shiying','-keyalg','RSA','-keysize','3072',
         '-validity','10000','-storepass:env','SHIYING_KEY_PASSWORD','-keypass:env','SHIYING_KEY_PASSWORD',
         '-dname','CN=ShiYing Local, OU=Personal Research, O=ShiYing, C=CN','-storetype','JKS'])
output=root/'dist'/'拾影-安卓版-v1.7.0.apk'
print('Signing installable APK...',flush=True)
run([jdk/'bin'/'java.exe','-jar',build_tools/'lib'/'apksigner.jar','sign','--ks',key,'--ks-key-alias','shiying',
     '--ks-pass','env:SHIYING_KEY_PASSWORD','--key-pass','env:SHIYING_KEY_PASSWORD','--out',output,aligned])
run([jdk/'bin'/'java.exe','-jar',build_tools/'lib'/'apksigner.jar','verify','--verbose','--print-certs',output])
report={'apk':output.name,'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'package':'cn.shiying.mobile','version':'1.7.0','version_code':11,'min_sdk':26,'target_sdk':35,'signing':'release, v2/v3 verified'}
(android/'verification').mkdir(exist_ok=True)
(android/'verification'/'build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
